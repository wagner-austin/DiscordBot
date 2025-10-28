from __future__ import annotations

import contextlib
import logging
import math
import os
import subprocess
import tempfile
from dataclasses import dataclass
from typing import BinaryIO, Literal, Protocol, runtime_checkable

from ...utils.errors import UserInputError
from .chunker import AudioChunker
from .merger import TranscriptMerger
from .parallel import ParallelTranscriber
from .types import TranscriptOptions, TranscriptSegment
from .whisper_parse import convert_verbose_to_segments


@runtime_checkable
class TranscriptProvider(Protocol):
    def fetch(self, video_id: str, opts: TranscriptOptions) -> list[TranscriptSegment]: ...


@dataclass
class STTTranscriptProvider:
    api_key: str
    max_video_seconds: int
    max_file_mb: int
    timeout_seconds: float = 900.0
    max_retries: int = 2
    cookies_text: str | None = None
    cookies_path: str | None = None
    # Chunking configuration (disabled by default for backward-compat and tests)
    enable_chunking: bool = False
    chunk_threshold_mb: float = 20.0
    target_chunk_mb: float = 20.0
    max_chunk_duration: float = 600.0
    max_concurrent_chunks: int = 3
    silence_threshold_db: float = -40.0
    silence_duration: float = 0.5
    # Estimation parameters
    stt_rtf: float = 0.5  # processing seconds per audio second
    dl_mib_per_sec: float = 4.0  # approximate download throughput for audio

    def __post_init__(self) -> None:
        self._logger = logging.getLogger(__name__)
        # OpenAI client uses env var by default, but we pass explicit for clarity
        os.environ.setdefault("OPENAI_API_KEY", self.api_key)
        from openai import OpenAI  # local import to avoid import-time dependency

        # Use extended timeouts and retries to avoid ReadTimeout on long jobs
        self._client = OpenAI(
            api_key=self.api_key,
            timeout=self.timeout_seconds,
            max_retries=self.max_retries,
        )

        # Track temporary cookies file (used if cookies_text provided)
        self._temp_cookies_file: str | None = None
        if self.cookies_text and not self.cookies_path:
            import base64
            import binascii

            try:
                decoded = base64.b64decode(self.cookies_text).decode("utf-8")
                fd, path = tempfile.mkstemp(prefix="ytcookies_", suffix=".txt", text=True)
                with os.fdopen(fd, "w") as f:
                    f.write(decoded)
                self._temp_cookies_file = path
                self._logger.debug("Using cookies from TEXT (temp file): %s", path)
            except (binascii.Error, UnicodeDecodeError, OSError) as e:
                self._logger.warning("Failed to use TRANSCRIPT_COOKIES_TEXT: %s", e)

    def __del__(self) -> None:
        """Clean up temporary cookies file if created."""
        path = getattr(self, "_temp_cookies_file", None)
        if path:
            with contextlib.suppress(Exception):
                os.remove(path)

    def fetch(self, video_id: str, opts: TranscriptOptions) -> list[TranscriptSegment]:
        url = f"https://www.youtube.com/watch?v={video_id}"
        # 1) Probe and validate duration
        duration = self._probe_or_error(video_id, url)
        self._logger.info("Probe complete: duration=%ss", duration)

        # 2) Download audio and get size
        audio_path: str | None = None
        try:
            audio_path, size_bytes = self._download_or_error(url, video_id)

            # 3) If size exceeds hard limit, handle via chunking or error
            if self._is_over_limit(size_bytes):
                return self._handle_over_limit(audio_path, size_bytes)

            # 4) Otherwise choose strategy (maybe chunk) and transcribe
            return self._transcribe_with_strategy(audio_path)
        finally:
            if audio_path:
                with contextlib.suppress(Exception):
                    os.remove(audio_path)

    # --- Helpers to reduce fetch complexity ---

    def _probe_or_error(self, video_id: str, url: str) -> int:
        try:
            self._logger.info("Probing video for STT: vid=%s url=%s", video_id, url)
            info = self._probe(url)
            duration = int(_as_float(info.get("duration", 0)))
            if self.max_video_seconds > 0 and duration and duration > self.max_video_seconds:
                allowed_min = max(1, math.ceil(self.max_video_seconds / 60))
                actual_min = max(1, math.ceil(duration / 60))
                raise UserInputError(
                    f"Video is too long for STT transcription ({actual_min} min). "
                    f"Maximum allowed: {allowed_min} min."
                )
            return duration
        except UserInputError:
            raise
        except Exception as e:
            self._logger.exception(
                "Failed to probe video for STT: type=%s msg=%s", type(e).__name__, str(e)
            )
            raise UserInputError("Failed to retrieve video information for transcription") from None

    def _download_or_error(self, url: str, video_id: str) -> tuple[str, int]:
        try:
            self._logger.info("Starting audio download: vid=%s", video_id)
            audio_path = self._download_audio(url)
            try:
                stat = os.stat(audio_path)
                self._logger.info("Audio downloaded: path=%s bytes=%s", audio_path, stat.st_size)
            except OSError:
                self._logger.debug("Could not stat downloaded audio at %s", audio_path)
                stat = os.stat(audio_path)
            return audio_path, stat.st_size
        except Exception as e:
            self._logger.exception(
                "Failed to download audio for STT: type=%s msg=%s", type(e).__name__, str(e)
            )
            raise UserInputError(
                "Could not download audio for transcription (unavailable or blocked)."
            ) from None

    def _is_over_limit(self, size_bytes: int) -> bool:
        if self.max_file_mb <= 0:
            return False
        max_bytes = self.max_file_mb * 1024 * 1024
        return size_bytes > max_bytes

    def _handle_over_limit(self, audio_path: str, size_bytes: int) -> list[TranscriptSegment]:
        actual_mb = size_bytes / (1024 * 1024)
        if self.enable_chunking and self._ffmpeg_available():
            self._logger.info(
                "Audio size %.1fMB exceeds limit %.1fMB; chunking enabled",
                actual_mb,
                float(self.max_file_mb),
            )
            try:
                result = self._transcribe_chunked(audio_path)
                self._logger.info(
                    "Whisper transcription (chunked) complete: segments=%s", len(result)
                )
                return result
            except Exception as e:
                self._logger.exception(
                    "Chunked transcription failed: type=%s msg=%s", type(e).__name__, str(e)
                )
                raise UserInputError("Failed to process audio file. Please try again.") from None
        raise UserInputError(
            f"Audio file is too large for Whisper API ({actual_mb:.1f} MB). "
            f"Maximum allowed: {self.max_file_mb} MB."
        )

    def _transcribe_with_strategy(self, audio_path: str) -> list[TranscriptSegment]:
        try:
            size_bytes = os.path.getsize(audio_path)
        except OSError:
            size_bytes = 0
        self._logger.info("Calling Whisper transcription: size_bytes=%s", size_bytes)
        try:
            if self.enable_chunking and self._should_chunk(audio_path):
                result = self._transcribe_chunked(audio_path)
            else:
                result = self._transcribe(audio_path)
            self._logger.info("Whisper transcription complete: segments=%s", len(result))
            return result
        except Exception as e:
            self._logger.exception(
                "STT transcription error: type=%s msg=%s", type(e).__name__, str(e)
            )
            raise UserInputError(
                "Transcription failed due to an API error. Please try again."
            ) from None

    def _probe(self, url: str) -> dict[str, object]:
        import yt_dlp  # local import to avoid import-time dependency

        ydl_opts: dict[str, object] = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "cachedir": False,
        }
        # Use cookies_path if provided, otherwise use temp file from cookies_text
        cookies_file = self.cookies_path or self._temp_cookies_file
        if cookies_file:
            ydl_opts["cookiefile"] = cookies_file
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_obj = ydl.extract_info(url, download=False)
            if not isinstance(info_obj, dict):
                raise UserInputError("Failed to probe video information")
            return info_obj

    def _download_audio(self, url: str) -> str:
        import yt_dlp  # local import to avoid import-time dependency

        tmpdir = tempfile.mkdtemp(prefix="ytstt_")
        # Try to get m4a/webm audio without re-encoding; avoid postprocessors
        outtmpl = os.path.join(tmpdir, "audio.%(ext)s")
        ydl_opts: dict[str, object] = {
            "format": "bestaudio/best",
            "outtmpl": outtmpl,
            "quiet": True,
            "noprogress": True,
            "no_warnings": True,
            "restrictfilenames": True,
            "overwrites": True,
            # no postprocessors -> avoid requiring ffmpeg when possible
            "postprocessors": [],
            "cachedir": False,
        }
        # Use cookies_path if provided, otherwise use temp file from cookies_text
        cookies_file = self.cookies_path or self._temp_cookies_file
        if cookies_file:
            ydl_opts["cookiefile"] = cookies_file
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            # Prefer requested_downloads filepath if present
            path: str | None = None
            reqs = info.get("requested_downloads") or []
            if reqs and isinstance(reqs, list):
                file0 = reqs[0]
                path = file0.get("filepath") if isinstance(file0, dict) else None
            if not path:
                # Fallback to prepared name
                path = ydl.prepare_filename(info)
            if not path or not os.path.exists(path):
                raise UserInputError("Failed to download audio for transcription")
            return path

    def _transcribe(self, audio_path: str) -> list[TranscriptSegment]:
        # Request verbose JSON for timestamped segments
        with open(audio_path, "rb") as f:
            resp = self._client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                response_format="verbose_json",
            )
        return convert_verbose_to_segments(resp)

    # --- Chunking helpers ---

    def _ffmpeg_available(self) -> bool:
        from shutil import which

        return bool(which("ffmpeg") and which("ffprobe"))

    def _should_chunk(self, audio_path: str) -> bool:
        if not self.enable_chunking:
            return False
        try:
            size_mb = os.path.getsize(audio_path) / (1024 * 1024)
        except OSError:
            return False
        return size_mb > float(self.chunk_threshold_mb)

    def _get_audio_duration(self, audio_path: str) -> float:
        import json

        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            audio_path,
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            data = json.loads(result.stdout or "{}")
            return float(data.get("format", {}).get("duration", 0.0))
        except (OSError, subprocess.TimeoutExpired, ValueError):
            # Fallback to 0 if ffprobe missing or errors
            return 0.0

    def _transcribe_chunked(self, audio_path: str) -> list[TranscriptSegment]:
        if not self._ffmpeg_available():
            raise UserInputError("ffmpeg/ffprobe not available; cannot chunk audio")
        # 1) Duration + size
        duration = self._get_audio_duration(audio_path)
        size_mb = os.path.getsize(audio_path) / (1024 * 1024)
        # 2) Chunk audio
        chunker = AudioChunker(
            target_chunk_mb=float(self.target_chunk_mb),
            max_chunk_duration_seconds=float(self.max_chunk_duration),
            silence_threshold_db=float(self.silence_threshold_db),
            silence_duration_seconds=float(self.silence_duration),
            logger=self._logger,
        )
        chunks = chunker.chunk_audio(audio_path, duration, size_mb)
        # If single passthrough chunk, use default path
        if len(chunks) == 1 and os.path.abspath(chunks[0].path) == os.path.abspath(audio_path):
            return self._transcribe(audio_path)

        # 3) Transcribe chunks concurrently
        def _do_transcribe(
            *,
            model: str,
            file: BinaryIO,
            response_format: Literal["verbose_json"],
            timeout: float | None = None,
        ) -> object:
            return self._client.audio.transcriptions.create(
                model=model,
                file=file,
                response_format=response_format,
                timeout=timeout,
            )

        transcriber = ParallelTranscriber(
            transcribe=_do_transcribe,
            max_concurrent=int(self.max_concurrent_chunks),
            max_retries=int(self.max_retries),
            timeout_seconds=float(self.timeout_seconds),
            logger=self._logger,
        )
        try:
            results = transcriber.transcribe_chunks(chunks)
            merger = TranscriptMerger()
            return merger.merge(list(zip(chunks, results, strict=False)))
        finally:
            # Clean up chunk files (not the original)
            for c in chunks:
                if os.path.abspath(c.path) != os.path.abspath(audio_path):
                    with contextlib.suppress(Exception):
                        os.remove(c.path)

    def estimate(self, url: str) -> tuple[int, float]:
        """Return (duration_seconds, approx_audio_size_mb) before download.

        Uses yt_dlp "formats" to find bestaudio filesize or estimates from abr.
        """
        info = self._probe(url)
        duration = int(_as_float(info.get("duration", 0)))
        approx_mb = 0.0
        # Try formats
        fmts = info.get("formats")
        best_abr = 0.0
        if isinstance(fmts, list):
            for fmt in fmts:
                if not isinstance(fmt, dict):
                    continue
                vcodec = fmt.get("vcodec", "")
                acodec = fmt.get("acodec", "")
                if vcodec and vcodec != "none":
                    continue  # skip video formats
                if not acodec or acodec == "none":
                    continue
                abr = _as_float(fmt.get("abr", 0.0))  # kbps
                size_bytes = fmt.get("filesize") or fmt.get("filesize_approx")
                size_mb = (
                    float(size_bytes) / (1024 * 1024)
                    if isinstance(size_bytes, int | float)
                    else 0.0
                )
                # prefer explicit size
                if size_mb > approx_mb:
                    approx_mb = size_mb
                if abr > best_abr:
                    best_abr = abr
        if approx_mb <= 0.0 and duration > 0 and best_abr > 0.0:
            approx_mb = (best_abr * 1000.0 / 8.0) * duration / (1024 * 1024)
        return max(0, duration), max(0.0, approx_mb)

    def estimate_eta_minutes(self, duration_seconds: int, approx_size_mb: float) -> int:
        """Estimate total minutes to process given duration/size.

        Models download time and STT processing time. If chunking is likely, accounts
        for concurrency and chunk-duration limits to reduce wall-clock estimate.
        """
        dur_s = max(0, int(duration_seconds))
        size_mb = max(0.0, float(approx_size_mb))
        # Download estimate (MiB/s)
        dl_time_min = (size_mb / self.dl_mib_per_sec) if self.dl_mib_per_sec > 0 else 0.0
        # Processing estimate
        will_chunk = (
            self.enable_chunking
            and (size_mb > float(self.chunk_threshold_mb) or size_mb > float(self.max_file_mb))
            and self._ffmpeg_available()
        )
        if not will_chunk or dur_s == 0:
            proc_min = (dur_s * float(self.stt_rtf)) / 60.0
        else:
            # Number of chunks by size and by max duration
            n_by_size = int(math.ceil(max(1e-6, size_mb) / float(self.target_chunk_mb)))
            n_by_dur = int(math.ceil(max(1e-6, dur_s) / float(self.max_chunk_duration)))
            n_chunks = max(1, max(n_by_size, n_by_dur))
            # Effective parallelism limited by configured concurrency and number of chunks
            parallel = max(1, min(int(self.max_concurrent_chunks), n_chunks))
            # Total processing time ~ total audio seconds divided by parallel workers, scaled by rtf
            proc_min = ((dur_s / parallel) * float(self.stt_rtf)) / 60.0
        return max(1, int(proc_min + dl_time_min + 0.5))


def _as_float(val: object) -> float:
    if isinstance(val, int | float):
        return float(val)
    if isinstance(val, str):
        try:
            return float(val)
        except ValueError:
            return 0.0
    return 0.0


# No legacy shims retained; parsing handled by whisper_parse.convert_verbose_to_segments
