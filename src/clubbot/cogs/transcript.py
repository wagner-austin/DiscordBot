from __future__ import annotations

import asyncio
import contextlib
import io
import logging
import os
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
        self._queue: JobQueueProto[TranscriptJob] = build_queue()
        # Announce queue backend for observability
        if os.getenv("UPSTASH_REDIS_REST_URL") and os.getenv("UPSTASH_REDIS_REST_TOKEN"):
            logging.getLogger(__name__).info(
                "Queue backend: Upstash REST (commands endpoints) with memory fallback"
            )
        else:
            logging.getLogger(__name__).info("Queue backend: Memory (Upstash not configured)")
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
            poll_interval=2.0,
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
        file = discord.File(fp=io.BytesIO(data), filename=fname)
        await interaction.followup.send(content=header, file=file, ephemeral=not public)
        log.info("Transcript sent successfully for vid=%s", result.video_id)

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
                    "Video is too long for transcription (> "
                    f"{allowed_min} min). Detected length: {actual_min} min."
                ),
            )
            return True

        max_mb = float(getattr(self.config, "TRANSCRIPT_MAX_FILE_MB", 0))
        if approx_mb and max_mb > 0 and approx_mb > max_mb:
            await self.handle_user_error(
                interaction,
                log,
                (
                    f"Audio file exceeds {int(max_mb)} MB limit for transcription "
                    f"(estimated ~{int(approx_mb)} MB)."
                ),
            )
            return True

        # Queue the job
        await self._queue.enqueue(TranscriptJob(request_id=req_id, url=url, user_id=user_id))
        est_min = max(1, int((dur_s + 59) // 60)) if dur_s else "?"
        size_txt = f"~{int(approx_mb)} MB" if approx_mb else "unknown size"
        # Estimate processing time (excludes queue delays)
        eta_min: str | int = "?"
        if dur_s:
            rtf = float(getattr(self.config, "TRANSCRIPT_STT_RTF", 0.5))
            dl_rate = float(getattr(self.config, "TRANSCRIPT_DL_MIB_PER_SEC", 4.0))
            dl_min = (approx_mb / dl_rate) if approx_mb else 0.0
            proc_min = (dur_s * rtf) / 60.0
            eta_min = max(1, int(proc_min + dl_min + 0.5))
        note = ""
        if not approx_mb and max_mb > 0:
            note = f" Note: size unknown; may exceed {int(max_mb)} MB limit."
        await interaction.followup.send(
            (
                f"Queued transcription for <{url}> (Length {est_min} min, {size_txt}; "
                f"ETA ~{eta_min} min).{note}\n"
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
        mins = int(elapsed_s // 60)
        secs = int(elapsed_s % 60)
        eta_txt = f"~{mins} min {secs}s" if mins > 0 else f"~{secs}s"

        header = f"Transcript for <{res.url}> (req={job.request_id})"
        content = f"{header}\nCompleted in {eta_txt}"
        data = res.text.encode("utf-8")
        file = discord.File(fp=io.BytesIO(data), filename=f"transcript_{res.video_id}.txt")
        await self.dm_file(job.user_id, content, file)
        logging.getLogger(__name__).info(
            "Transcript job completed req=%s elapsed=%.2fs", job.request_id, elapsed_s
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
