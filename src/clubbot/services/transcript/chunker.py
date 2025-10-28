from __future__ import annotations

import contextlib
import logging
import math
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass

from .types import AudioChunk

_SILENCE_START_RE = re.compile(r"silence_start:\s*(?P<ts>[0-9]+(?:\.[0-9]+)?)")
_SILENCE_END_RE = re.compile(r"silence_end:\s*(?P<ts>[0-9]+(?:\.[0-9]+)?)")


@dataclass(frozen=True)
class _SplitWindow:
    start: float
    end: float


class AudioChunker:
    """Split audio files at optimal points (silence when possible).

    Uses ffmpeg/ffprobe and stream copy to avoid re-encoding for speed.
    """

    def __init__(
        self,
        *,
        target_chunk_mb: float = 20.0,
        max_chunk_duration_seconds: float = 600.0,
        silence_threshold_db: float = -40.0,
        silence_duration_seconds: float = 0.5,
        logger: logging.Logger | None = None,
        ffmpeg_path: str = "ffmpeg",
        ffprobe_path: str = "ffprobe",
    ) -> None:
        self._target_chunk_mb = max(1.0, float(target_chunk_mb))
        self._max_chunk_dur = max(1.0, float(max_chunk_duration_seconds))
        self._silence_db = float(silence_threshold_db)
        self._silence_min = max(0.1, float(silence_duration_seconds))
        self._logger = logger or logging.getLogger(__name__)
        self._ffmpeg = ffmpeg_path
        self._ffprobe = ffprobe_path

    def chunk_audio(
        self, audio_path: str, total_duration: float, estimated_mb: float
    ) -> list[AudioChunk]:
        """Return chunk descriptors. If no chunking needed, return a single pass-through chunk."""
        size_mb = self._safe_size_mb(audio_path)
        est_mb = estimated_mb or size_mb
        if est_mb <= self._target_chunk_mb and total_duration <= self._max_chunk_dur:
            return [
                AudioChunk(
                    path=audio_path,
                    start_seconds=0.0,
                    duration_seconds=max(0.0, float(total_duration)),
                    size_bytes=os.path.getsize(audio_path),
                )
            ]

        self._logger.info(
            "Chunking audio: size=%.1fMB duration=%.1fs target=%.1fMB",
            est_mb,
            total_duration,
            self._target_chunk_mb,
        )

        silence_points = self._detect_silence(audio_path, total_duration)
        split_points = self._calculate_split_points(silence_points, total_duration, est_mb)
        return self._split_audio(audio_path, split_points, total_duration)

    def _safe_size_mb(self, audio_path: str) -> float:
        try:
            return os.path.getsize(audio_path) / (1024 * 1024)
        except OSError:
            return 0.0

    def _detect_silence(self, audio_path: str, duration: float) -> list[float]:
        """Run ffmpeg silencedetect and parse timestamps (prefer silence_end as split)."""
        cmd = [
            self._ffmpeg,
            "-i",
            audio_path,
            "-af",
            f"silencedetect=n={self._silence_db}dB:d={self._silence_min}",
            "-f",
            "null",
            "-",
        ]
        self._logger.debug("Running silencedetect: %s", " ".join(cmd))
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        except (subprocess.TimeoutExpired, OSError) as e:  # pragma: no cover - depends on system
            self._logger.warning("Silence detection failed to run: %s", e)
            return []
        out = (proc.stdout or "") + (proc.stderr or "")
        points: list[float] = []
        for line in out.splitlines():
            m_end = _SILENCE_END_RE.search(line)
            if m_end:
                try:
                    points.append(float(m_end.group("ts")))
                except ValueError:
                    continue
        self._logger.debug("Detected %d silence points in %.1fs audio", len(points), duration)
        return points

    def _calculate_split_points(
        self, silence_points: list[float], total_duration: float, estimated_mb: float
    ) -> list[float]:
        """Determine optimal split points based on target size and detected silence.

        Returns a monotonically increasing list of split timestamps (seconds) within (0, duration).
        """
        num_chunks = max(1, int(math.ceil(max(1e-6, estimated_mb) / self._target_chunk_mb)))
        ideal: list[float] = [(total_duration / num_chunks) * i for i in range(1, num_chunks)]
        if not ideal:
            return []
        # Also honor max_chunk_duration by inserting additional ideal points
        if total_duration / num_chunks > self._max_chunk_dur:
            extra = int(math.ceil(total_duration / self._max_chunk_dur))
            ideal = [(total_duration / extra) * i for i in range(1, extra)]

        if not silence_points:
            return ideal

        tolerance_ratio = 0.30
        out: list[float] = []
        for t in ideal:
            tol = max(1.0, total_duration * tolerance_ratio / max(1, len(ideal)))
            # Find nearest silence within tolerance window
            nearest = min(silence_points, key=lambda s: abs(s - t))
            if abs(nearest - t) <= tol:
                out.append(nearest)
                self._logger.debug("Split at %.1fs (silence near ideal %.1fs)", nearest, t)
            else:
                out.append(t)
                self._logger.debug("Split at %.1fs (no nearby silence)", t)
        # De-dupe and sort
        return sorted({x for x in out if 0 < x < total_duration})

    def _split_audio(
        self, audio_path: str, split_points: list[float], total_duration: float
    ) -> list[AudioChunk]:
        container, codec = self._probe_stream_info(audio_path)
        # Choose an output extension that is container/codec-compatible for stream copy.
        # Prefer webm for opus; otherwise use m4a.
        ext = "webm" if codec == "opus" else "m4a"
        if not split_points:
            # Single pass-through chunk
            return [
                AudioChunk(
                    path=audio_path,
                    start_seconds=0.0,
                    duration_seconds=max(0.0, float(total_duration)),
                    size_bytes=os.path.getsize(audio_path),
                )
            ]

        segments: list[_SplitWindow] = []
        last = 0.0
        for s in split_points:
            s_clamped = min(max(0.0, s), total_duration)
            if s_clamped > last:
                segments.append(_SplitWindow(start=last, end=s_clamped))
                last = s_clamped
        if last < total_duration:
            segments.append(_SplitWindow(start=last, end=total_duration))

        # Log the planned chunking strategy for observability
        self._logger.info(
            "Chunking plan: input_format=%s codec=%s out_ext=.%s parts=%d",
            container or "?",
            codec or "?",
            ext,
            len(segments),
        )

        outdir = tempfile.mkdtemp(prefix="ytstt_chunks_")
        created: list[AudioChunk] = []
        for idx, seg in enumerate(segments):
            out_path = os.path.join(outdir, f"chunk_{idx:03d}.{ext}")
            # Primary attempt: stream copy (fast, no re-encode)
            copy_cmd = [
                self._ffmpeg,
                "-ss",
                f"{seg.start:.3f}",
                "-to",
                f"{seg.end:.3f}",
                "-i",
                audio_path,
                "-c",
                "copy",
                "-y",
                out_path,
            ]
            self._logger.debug("Creating chunk (copy): %s", " ".join(copy_cmd))
            try:
                subprocess.run(copy_cmd, check=True, capture_output=True, text=True, timeout=180)
            except subprocess.CalledProcessError:
                # Fallback: re-encode to AAC in m4a container for broad compatibility
                reencode_cmd = [
                    self._ffmpeg,
                    "-ss",
                    f"{seg.start:.3f}",
                    "-to",
                    f"{seg.end:.3f}",
                    "-i",
                    audio_path,
                    "-c:a",
                    "aac",
                    "-b:a",
                    "128k",
                    "-movflags",
                    "+faststart",
                    "-y",
                    out_path,
                ]
                self._logger.debug("Creating chunk (reencode): %s", " ".join(reencode_cmd))
                try:
                    subprocess.run(
                        reencode_cmd, check=True, capture_output=True, text=True, timeout=300
                    )
                except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
                    self._logger.exception("ffmpeg re-encode split failed: %s", e)
                    self._cleanup_dir(outdir)
                    raise
            except (subprocess.TimeoutExpired, OSError, subprocess.SubprocessError) as e:
                self._logger.exception("ffmpeg split error: %s", e)
                self._cleanup_dir(outdir)
                raise
            # Get size and append chunk (inside for loop)
            try:
                sz = os.path.getsize(out_path)
            except OSError:
                sz = 0
            created.append(
                AudioChunk(
                    path=out_path,
                    start_seconds=seg.start,
                    duration_seconds=max(0.0, seg.end - seg.start),
                    size_bytes=sz,
                )
            )
        return created

    def _cleanup_dir(self, path: str) -> None:
        with contextlib.suppress(Exception):
            shutil.rmtree(path)

    def _probe_stream_info(self, audio_path: str) -> tuple[str, str]:
        """Return (container_format, audio_codec) using ffprobe. Empty strings on failure."""
        import json

        cmd = [
            self._ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=format_name,format_long_name",
            "-show_streams",
            "-of",
            "json",
            audio_path,
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        except (subprocess.TimeoutExpired, OSError):  # pragma: no cover - environment dependent
            return "", ""
        try:
            data = json.loads(proc.stdout or proc.stderr or "{}")
        except ValueError:
            return "", ""
        fmt = data.get("format", {}) if isinstance(data, dict) else {}
        container = str(fmt.get("format_name", "")) if isinstance(fmt, dict) else ""
        codec = ""
        streams = data.get("streams", []) if isinstance(data, dict) else []
        if isinstance(streams, list):
            for s in streams:
                if not isinstance(s, dict):
                    continue
                if s.get("codec_type") == "audio":
                    codec = str(s.get("codec_name") or "")
                    break
        return container, codec
