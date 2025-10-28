from __future__ import annotations

import logging
import os
import tempfile
from dataclasses import dataclass

import pytest
from src.clubbot.services.transcript.parallel import TranscribeFn
from src.clubbot.services.transcript.stt_provider import STTTranscriptProvider
from src.clubbot.services.transcript.types import AudioChunk, TranscriptOptions, TranscriptSegment


def _touch_file(bytes_size: int) -> str:
    fd, path = tempfile.mkstemp(prefix="stt_chunk_test_", suffix=".bin")
    with os.fdopen(fd, "wb") as f:
        f.write(b"0" * bytes_size)
    return path


@dataclass
class NoopSTT(STTTranscriptProvider):
    def __post_init__(self) -> None:
        # Skip OpenAI client init for unit tests
        self._logger = logging.getLogger(__name__)
        self._client = object()


def test_stt_provider_chunked_over_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    p = NoopSTT(api_key="test", max_video_seconds=9999, max_file_mb=1, enable_chunking=True)
    # Probe ok
    monkeypatch.setattr(p, "_probe", lambda url: {"duration": 60})
    # Simulate ffmpeg presence
    monkeypatch.setattr(p, "_ffmpeg_available", lambda: True)
    # Build a file bigger than 1 MB to force over-limit path
    big = _touch_file(2 * 1024 * 1024)
    try:
        monkeypatch.setattr(p, "_download_audio", lambda url: big)
        # Avoid real duration probing in chunked path
        monkeypatch.setattr(p, "_get_audio_duration", lambda ap: 30.0)

        # Stub chunker to return two chunks with different start offsets
        class StubChunker:
            def __init__(
                self,
                *,
                target_chunk_mb: float,
                max_chunk_duration_seconds: float,
                silence_threshold_db: float,
                silence_duration_seconds: float,
                logger: logging.Logger | None,
            ) -> None:
                self.target_chunk_mb = target_chunk_mb
                self.max_chunk_duration_seconds = max_chunk_duration_seconds
                self.silence_threshold_db = silence_threshold_db
                self.silence_duration_seconds = silence_duration_seconds
                self.logger = logger

            def chunk_audio(self, ap: str, duration: float, size_mb: float) -> list[AudioChunk]:
                # Create two temp chunk files
                fd1, p1 = tempfile.mkstemp(prefix="chunk_", suffix=".webm")
                os.close(fd1)
                fd2, p2 = tempfile.mkstemp(prefix="chunk_", suffix=".webm")
                os.close(fd2)
                return [
                    AudioChunk(path=p1, start_seconds=0.0, duration_seconds=10.0, size_bytes=0),
                    AudioChunk(path=p2, start_seconds=10.0, duration_seconds=10.0, size_bytes=0),
                ]

        # Replace AudioChunker class in provider module
        import src.clubbot.services.transcript.stt_provider as sp

        monkeypatch.setattr(sp, "AudioChunker", StubChunker)

        # Dummy transcriber returns one segment per chunk starting at 0.0
        class StubTranscriber:
            def __init__(
                self,
                *,
                transcribe: TranscribeFn,
                max_concurrent: int,
                max_retries: int,
                timeout_seconds: float,
                logger: logging.Logger | None,
            ) -> None:
                self.transcribe = transcribe
                self.max_concurrent = max_concurrent
                self.max_retries = max_retries
                self.timeout_seconds = timeout_seconds
                self.logger = logger

            def transcribe_chunks(self, chunks: list[AudioChunk]) -> list[list[TranscriptSegment]]:
                return [
                    [TranscriptSegment(text="a", start=0.0, duration=1.0)],
                    [TranscriptSegment(text="b", start=0.0, duration=1.0)],
                ]

        monkeypatch.setattr(sp, "ParallelTranscriber", StubTranscriber)

        out = p.fetch("abc123xyz00", TranscriptOptions(preferred_langs=["en"]))
        assert [s.text for s in out] == ["a", "b"]
        assert out[0].start == 0.0 and out[1].start == 10.0
    finally:
        with __import__("contextlib").suppress(Exception):
            os.remove(big)


def test_stt_provider_threshold_chunking(monkeypatch: pytest.MonkeyPatch) -> None:
    # High hard limit so we do not trigger over-limit; threshold will trigger chunking instead
    p = NoopSTT(
        api_key="test",
        max_video_seconds=9999,
        max_file_mb=500,
        enable_chunking=True,
        chunk_threshold_mb=1.0,
    )
    monkeypatch.setattr(p, "_probe", lambda url: {"duration": 60})
    monkeypatch.setattr(p, "_ffmpeg_available", lambda: True)
    small = _touch_file(2 * 1024 * 1024)  # 2 MB > threshold 1 MB
    try:
        monkeypatch.setattr(p, "_download_audio", lambda url: small)
        monkeypatch.setattr(p, "_get_audio_duration", lambda ap: 30.0)

        # Reuse the same fake chunker/transcriber setup
        import src.clubbot.services.transcript.stt_provider as sp

        class StubChunker2:
            def __init__(
                self,
                *,
                target_chunk_mb: float,
                max_chunk_duration_seconds: float,
                silence_threshold_db: float,
                silence_duration_seconds: float,
                logger: logging.Logger | None,
            ) -> None:
                self.target_chunk_mb = target_chunk_mb
                self.max_chunk_duration_seconds = max_chunk_duration_seconds
                self.silence_threshold_db = silence_threshold_db
                self.silence_duration_seconds = silence_duration_seconds
                self.logger = logger

            def chunk_audio(self, ap: str, duration: float, size_mb: float) -> list[AudioChunk]:
                fd1, p1 = tempfile.mkstemp(prefix="chunk_", suffix=".m4a")
                os.close(fd1)
                fd2, p2 = tempfile.mkstemp(prefix="chunk_", suffix=".m4a")
                os.close(fd2)
                return [
                    AudioChunk(path=p1, start_seconds=0.0, duration_seconds=10.0, size_bytes=0),
                    AudioChunk(path=p2, start_seconds=10.0, duration_seconds=10.0, size_bytes=0),
                ]

        class StubTranscriber2:
            def __init__(
                self,
                *,
                transcribe: TranscribeFn,
                max_concurrent: int,
                max_retries: int,
                timeout_seconds: float,
                logger: logging.Logger | None,
            ) -> None:
                self.transcribe = transcribe
                self.max_concurrent = max_concurrent
                self.max_retries = max_retries
                self.timeout_seconds = timeout_seconds
                self.logger = logger

            def transcribe_chunks(self, chunks: list[AudioChunk]) -> list[list[TranscriptSegment]]:
                return [
                    [TranscriptSegment(text="x", start=0.0, duration=1.0)],
                    [TranscriptSegment(text="y", start=0.0, duration=1.0)],
                ]

        monkeypatch.setattr(sp, "AudioChunker", StubChunker2)
        monkeypatch.setattr(sp, "ParallelTranscriber", StubTranscriber2)

        out = p.fetch("abc123xyz00", TranscriptOptions(preferred_langs=["en"]))
        assert [s.text for s in out] == ["x", "y"]
        assert out[0].start == 0.0 and out[1].start == 10.0
    finally:
        with __import__("contextlib").suppress(Exception):
            os.remove(small)
