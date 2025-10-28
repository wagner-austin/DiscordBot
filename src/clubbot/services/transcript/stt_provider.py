from __future__ import annotations

import contextlib
import logging
import math
import os
import tempfile
from dataclasses import dataclass
from typing import Protocol, TypedDict, runtime_checkable

from ...utils.errors import UserInputError
from .types import TranscriptOptions, TranscriptSegment


class _WhisperSegment(TypedDict):
    id: int
    start: float
    end: float
    text: str


class _WhisperVerbose(TypedDict):
    text: str
    segments: list[_WhisperSegment]


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

        # Track temporary cookies file (unused unless created elsewhere)
        self._temp_cookies_file: str | None = None

    def __del__(self) -> None:
        """Clean up temporary cookies file if created."""
        path = getattr(self, "_temp_cookies_file", None)
        if path:
            with contextlib.suppress(Exception):
                os.remove(path)

    def fetch(self, video_id: str, opts: TranscriptOptions) -> list[TranscriptSegment]:
        url = f"https://www.youtube.com/watch?v={video_id}"
        try:
            self._logger.info("Probing video for STT: vid=%s url=%s", video_id, url)
            info = self._probe(url)
            duration = int(_as_float(info.get("duration", 0)))
            self._logger.info("Probe complete: duration=%ss", duration)
            if self.max_video_seconds > 0 and duration and duration > self.max_video_seconds:
                allowed_min = max(1, math.ceil(self.max_video_seconds / 60))
                actual_min = max(1, math.ceil(duration / 60))
                raise UserInputError(
                    f"Video is too long for transcription (> {allowed_min} min). "
                    f"Detected length: {actual_min} min."
                )
        except UserInputError:
            # Bubble up user-facing errors without wrapping
            raise
        except Exception as e:
            self._logger.exception(
                "Failed to probe video for STT: type=%s msg=%s", type(e).__name__, str(e)
            )
            raise UserInputError("Failed to retrieve video information for transcription") from None

        audio_path: str | None = None
        try:
            try:
                self._logger.info("Starting audio download: vid=%s", video_id)
                audio_path = self._download_audio(url)
                try:
                    stat = os.stat(audio_path)
                    self._logger.info(
                        "Audio downloaded: path=%s bytes=%s", audio_path, stat.st_size
                    )
                except OSError:
                    self._logger.debug("Could not stat downloaded audio at %s", audio_path)
            except Exception as e:
                self._logger.exception(
                    "Failed to download audio for STT: type=%s msg=%s",
                    type(e).__name__,
                    str(e),
                )
                raise UserInputError(
                    "Could not download audio for transcription (unavailable or blocked)."
                ) from None

            stat = os.stat(audio_path)
            max_bytes = self.max_file_mb * 1024 * 1024
            if self.max_file_mb > 0 and stat.st_size > max_bytes:
                raise UserInputError(
                    f"Audio file exceeds {self.max_file_mb} MB limit for transcription."
                )
            try:
                self._logger.info("Calling Whisper transcription: size_bytes=%s", stat.st_size)
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
        finally:
            if audio_path:
                with contextlib.suppress(Exception):
                    os.remove(audio_path)

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

        data = _to_verbose_dict(resp)
        raw_segments = data["segments"]
        out: list[TranscriptSegment] = []
        for seg in raw_segments:
            text = seg.get("text", "").strip()
            if not text:
                continue
            start = _as_float(seg.get("start", 0.0))
            end = _as_float(seg.get("end", start))
            duration = max(0.0, end - start)
            out.append(TranscriptSegment(text=text, start=start, duration=duration))
        return out

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


def _as_float(val: object) -> float:
    if isinstance(val, int | float):
        return float(val)
    if isinstance(val, str):
        try:
            return float(val)
        except ValueError:
            return 0.0
    return 0.0


def _to_verbose_dict(obj: object) -> _WhisperVerbose:
    data: dict[str, object] | None = None
    # Try common model-to-dict methods
    for meth in ("to_dict_recursive", "to_dict", "model_dump"):
        f = getattr(obj, meth, None)
        if callable(f):
            # Suppress any vendor-specific conversion errors and try next
            with contextlib.suppress(Exception):
                result = f()
                if isinstance(result, dict):
                    data = result
                    break
    if data is None and isinstance(obj, dict):
        data = obj
    if data is None:
        return {"text": "", "segments": []}

    text = str(data.get("text", ""))
    segs_raw = data.get("segments")
    segs: list[_WhisperSegment] = []
    if isinstance(segs_raw, list):
        for item in segs_raw:
            if not isinstance(item, dict):
                continue
            seg_text = str(item.get("text", ""))
            start = _as_float(item.get("start", 0.0))
            end = _as_float(item.get("end", start))
            # id is optional; coerce to int index if missing
            raw_id = item.get("id", None)
            seg_id = int(_as_float(raw_id)) if raw_id is not None else len(segs)
            segs.append({"id": seg_id, "start": start, "end": end, "text": seg_text})
    return {"text": text, "segments": segs}
