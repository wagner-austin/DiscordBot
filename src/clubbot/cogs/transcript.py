from __future__ import annotations

import asyncio
import contextlib
import io
import logging
import time

import discord
from discord import app_commands
from discord.ext import commands

from ..config import Config, load_config
from ..logging import set_request_id
from ..services.jobs.helpers import (
    default_retry_policy_factory,
    failure_notifier_factory,
)
from ..services.jobs.queue import JobQueueProto, TranscriptJob, build_queue
from ..services.jobs.runner import JobRunner
from ..services.transcript.app import TranscriptService
from ..services.transcript.types import SupportsEstimate
from ..utils.errors import UserInputError
from ..utils.rate_limiter import RateLimiter
from ..utils.youtube import validate_youtube_url
from .base import BaseCog


class TranscriptCog(BaseCog):
    def __init__(
        self,
        bot: commands.Bot,
        config: Config,
        transcript_service: TranscriptService,
        queue: JobQueueProto[TranscriptJob] | None = None,
    ) -> None:
        super().__init__()
        self.bot = bot
        self.config = config
        self.transcript_service = transcript_service
        self.rate_limiter = RateLimiter(
            getattr(config, "TRANSCRIPT_RATE_LIMIT", 2),
            getattr(config, "TRANSCRIPT_RATE_WINDOW_SECONDS", 60),
        )
        # Background job queue and runner
        self._queue: JobQueueProto[TranscriptJob] = queue or build_queue()
        # Announce queue backend for observability
        backend_name = type(self._queue).__name__
        logging.getLogger(__name__).info(f"Queue backend: {backend_name}")
        # Build standardized failure and retry behavior for transcript jobs
        failure_cb = failure_notifier_factory(
            notify_fn=self.notify_user,
            user_error_type=UserInputError,
            service_name="transcription",
        )
        retry_policy = default_retry_policy_factory(UserInputError)

        self._runner = JobRunner[TranscriptJob](
            queue=self._queue,
            handler=self._handle_job,
            failure_callback=failure_cb,
            retry_policy=retry_policy,
            max_concurrency=1,
            retry_attempts=1,
            retry_backoff=1.0,
            idle_sleep=0.5,
            logger=logging.getLogger(__name__),
        )
        self._runner.start()

    @app_commands.command(
        name="transcript",
        description="Download and clean a YouTube video transcript",
    )
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.describe(url="YouTube video URL")
    async def transcript(self, interaction: discord.Interaction, url: str) -> None:
        if not await self._ack_interaction(interaction):
            return

        req_id = self.new_request_id()
        set_request_id(req_id)
        log = self.request_logger(req_id)
        user_id = self._extract_int_attr(interaction.user, "id")
        guild_id = self._extract_int_attr(getattr(interaction, "guild", None), "id")
        if user_id is None:
            await self.handle_user_error(
                interaction, log, "Could not determine your user id for rate limiting"
            )
            return
        log.debug("Transcript command invoked by user=%s guild=%s", user_id, guild_id)

        try:
            # Validate early that it's a YouTube URL for nice errors
            _ = validate_youtube_url(url)

            allowed, wait_s = self.rate_limiter.allow(user_id, "transcript")
            if not allowed:
                await interaction.followup.send(
                    f"Please wait {int(wait_s)} seconds before requesting another transcript",
                    ephemeral=not getattr(self.config, "TRANSCRIPT_PUBLIC_RESPONSES", False),
                )
                log.info("Rate limited user=%s", user_id)
                return

            # For STT provider, enqueue a background job after preflight estimate
            provider = (self.config.TRANSCRIPT_PROVIDER or "youtube").strip().lower()
            if provider == "stt":
                handled = await self._handle_stt_request(
                    interaction=interaction,
                    log=log,
                    url=url,
                    req_id=req_id,
                    user_id=user_id,
                )
                if handled:
                    return
            # Otherwise, fetch immediately (captions path)
            result = await asyncio.to_thread(self.transcript_service.fetch_cleaned, url)
        except UserInputError as e:
            await self.handle_user_error(interaction, log, str(e))
            return
        except Exception as exc:
            await self.handle_exception(interaction, log, exc)
            return

        public = getattr(self.config, "TRANSCRIPT_PUBLIC_RESPONSES", False)
        header = f"Transcript for <{result.url}>"
        # Always send as attachment to avoid spammy inline posts
        fname = f"transcript_{result.video_id}.txt"
        data = result.text.encode("utf-8")
        # Enforce attachment size limit
        if self._is_attachment_too_large(data):
            await self.handle_user_error(
                interaction,
                log,
                (
                    f"Transcript is too large to attach (> {self._get_attachment_limit_mb()} MB). "
                    "Please try a shorter video."
                ),
            )
            return
        file = discord.File(fp=io.BytesIO(data), filename=fname)
        await interaction.followup.send(content=header, file=file, ephemeral=not public)
        log.info("Transcript sent successfully for vid=%s", result.video_id)

    def _get_attachment_limit_mb(self) -> int:
        """Return the configured attachment size limit in MB (default 25)."""
        return int(getattr(self.config, "TRANSCRIPT_MAX_ATTACHMENT_MB", 25))

    def _is_attachment_too_large(self, data: bytes) -> bool:
        """True if payload exceeds the configured attachment limit."""
        limit_mb = self._get_attachment_limit_mb()
        return limit_mb > 0 and len(data) > limit_mb * 1024 * 1024

    async def _handle_stt_request(
        self,
        *,
        interaction: discord.Interaction,
        log: logging.LoggerAdapter[logging.Logger],
        url: str,
        req_id: str,
        user_id: int,
    ) -> bool:
        prov_obj = self.transcript_service.provider
        if isinstance(prov_obj, SupportsEstimate):
            dur_s, approx_mb = await asyncio.to_thread(prov_obj.estimate, url)
        else:
            dur_s, approx_mb = 0, 0.0

        # Early user-facing validation using estimates when available
        max_secs = getattr(self.config, "TRANSCRIPT_MAX_VIDEO_SECONDS", 0)
        if dur_s and max_secs > 0 and dur_s > max_secs:
            allowed_min = max(1, int((max_secs + 59) // 60))
            actual_min = max(1, int((dur_s + 59) // 60))
            await self.handle_user_error(
                interaction,
                log,
                (
                    f"Video is too long for STT transcription ({actual_min} min). "
                    f"Maximum allowed: {allowed_min} min."
                ),
            )
            return True

        max_mb = float(getattr(self.config, "TRANSCRIPT_MAX_FILE_MB", 0))
        chunking_enabled = bool(getattr(self.config, "TRANSCRIPT_ENABLE_CHUNKING", True))
        if approx_mb and max_mb > 0 and approx_mb > max_mb:
            can_chunk = False
            if chunking_enabled:
                try:
                    from shutil import which  # local import to avoid global dependency

                    can_chunk = bool(which("ffmpeg") and which("ffprobe"))
                except Exception:
                    can_chunk = False
            if not can_chunk:
                await self.handle_user_error(
                    interaction,
                    log,
                    (
                        f"Audio file is estimated at ~{int(approx_mb)} MB, which exceeds "
                        f"Whisper API's {int(max_mb)} MB limit. Try a shorter video."
                    ),
                )
                return True

        # Queue the job
        await self._queue.enqueue(
            TranscriptJob(request_id=req_id, url=url, user_id=user_id, queued_ts=time.time())
        )
        est_min = max(1, int((dur_s + 59) // 60)) if dur_s else "?"
        # Estimate transcript size (KB)
        kbpm = float(getattr(self.config, "TRANSCRIPT_ESTIMATED_TEXT_KB_PER_MIN", 1.0))
        est_kb = int((est_min if isinstance(est_min, int) else 0) * kbpm) if est_min != "?" else 0
        # Estimate processing time (excludes queue delays)
        eta_min: str | int = "?"
        if dur_s:
            # If provider supports refined ETA, use it; otherwise fallback to simple model
            prov_obj = self.transcript_service.provider
            from ..services.transcript.stt_provider import STTTranscriptProvider

            if isinstance(prov_obj, STTTranscriptProvider):
                eta_min = prov_obj.estimate_eta_minutes(dur_s, float(approx_mb))
            else:
                rtf = float(getattr(self.config, "TRANSCRIPT_STT_RTF", 0.5))
                dl_rate = float(getattr(self.config, "TRANSCRIPT_DL_MIB_PER_SEC", 4.0))
                dl_min = (approx_mb / dl_rate) if approx_mb else 0.0
                proc_min = (dur_s * rtf) / 60.0
                eta_min = max(1, int(proc_min + dl_min + 0.5))
        await interaction.followup.send(
            (
                f"Queued transcription for <{url}> (Length {est_min} min; "
                f"Estimated transcript ~{est_kb if est_kb else '?'} KB; ETA ~{eta_min} min).\n"
                f"We'll DM you when it's ready. Request: {req_id}"
            ),
            ephemeral=not getattr(self.config, "TRANSCRIPT_PUBLIC_RESPONSES", False),
        )
        log.info("Queued STT job req=%s url=%s", req_id, url[:50])
        return True

    async def _handle_job(self, job: TranscriptJob) -> None:
        start = time.perf_counter()
        res = await asyncio.to_thread(self.transcript_service.fetch_cleaned, job.url)
        elapsed_s = max(0.0, time.perf_counter() - start)
        # End-to-end time (including queue wait) if available
        e2e_s = 0.0
        if isinstance(job.queued_ts, float) and job.queued_ts > 0.0:
            e2e_s = max(0.0, time.time() - job.queued_ts)
        e2e_m = int(e2e_s // 60)
        e2e_sec = int(e2e_s % 60)
        e2e_txt = f"~{e2e_m} min {e2e_sec}s" if e2e_s > 0 else "~?s"

        header = f"Transcript for <{res.url}> (req={job.request_id})"
        content = f"{header}\nTotal time {e2e_txt}"
        data = res.text.encode("utf-8")
        # Enforce attachment size limit before DM
        if self._is_attachment_too_large(data):
            limit = self._get_attachment_limit_mb()
            await self.notify_user(
                job.user_id,
                (
                    f"Transcript is too large to attach (> {limit} MB) "
                    f"(req={job.request_id}). Please try a shorter video."
                ),
            )
            return
        file = discord.File(fp=io.BytesIO(data), filename=f"transcript_{res.video_id}.txt")
        await self.dm_file(job.user_id, content, file)
        logging.getLogger(__name__).info(
            "Transcript job completed req=%s elapsed=%.2fs e2e=%.2fs",
            job.request_id,
            elapsed_s,
            e2e_s,
        )

    # Failure handling and retry policy provided via helpers; no per-cog duplication

    # User notification helpers moved to BaseCog

    @staticmethod
    def _extract_int_attr(obj: object | None, name: str) -> int | None:
        if obj is None:
            return None
        value = getattr(obj, name, None)
        return value if isinstance(value, int) else None

    async def _ack_interaction(self, interaction: discord.Interaction) -> bool:
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(
                    ephemeral=not getattr(self.config, "TRANSCRIPT_PUBLIC_RESPONSES", False)
                )
            return True
        except discord.NotFound as e:
            logging.getLogger(__name__).debug("Interaction expired before defer; skipping: %s", e)
            return False
        except discord.HTTPException as e:
            if getattr(e, "code", None) == 40060:
                logging.getLogger(__name__).debug("Interaction already acknowledged")
                return True
            logging.getLogger(__name__).exception("Failed to defer interaction: %s", e)
            with contextlib.suppress(Exception):
                await interaction.followup.send(
                    "An error occurred. Please try again.", ephemeral=True
                )
            return False
        except Exception as e:  # pragma: no cover - unexpected
            logging.getLogger(__name__).exception("Failed to defer interaction: %s", e)
            with contextlib.suppress(Exception):
                await interaction.followup.send(
                    "An error occurred. Please try again.", ephemeral=True
                )
            return False


async def setup(bot: commands.Bot) -> None:  # pragma: no cover - manual extension
    cfg = load_config()
    service = TranscriptService(cfg)
    await bot.add_cog(TranscriptCog(bot, cfg, service))
