from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest
import src.clubbot.services.transcript.stt_provider as stt_mod
from src.clubbot.services.transcript.stt_provider import STTTranscriptProvider


def _patch_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(
        __import__("sys").modules,
        "openai",
        SimpleNamespace(
            OpenAI=lambda *a, **k: SimpleNamespace(
                audio=SimpleNamespace(transcriptions=SimpleNamespace(create=lambda **_: None))
            )
        ),
    )


def test_invalid_cookies_text_is_logged_and_ignored(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _patch_openai(monkeypatch)
    caplog.set_level(logging.WARNING)
    # Provide invalid base64 to trigger warning path
    p = STTTranscriptProvider(
        api_key="x",
        max_video_seconds=9999,
        max_file_mb=25,
        cookies_text="@@@invalid@@@",
        enable_chunking=False,
    )
    assert getattr(p, "_temp_cookies_file", None) is None
    assert any("Failed to use TRANSCRIPT_COOKIES_TEXT" in r.message for r in caplog.records)


def test_parallel_transcriber_receives_max_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_openai(monkeypatch)
    p = STTTranscriptProvider(
        api_key="x",
        max_video_seconds=9999,
        max_file_mb=25,
        enable_chunking=True,
    )
    monkeypatch.setattr(p, "_ffmpeg_available", lambda: True, raising=True)
    monkeypatch.setattr(p, "_get_audio_duration", lambda _p: 120.0, raising=True)
    monkeypatch.setattr(__import__("os").path, "getsize", lambda _p: 50 * 1024 * 1024, raising=True)

    # Fake chunker returns two chunks
    class _FakeChunker:
        def __init__(self, *a: object, **k: object) -> None:
            pass

        def chunk_audio(self, path: str, duration: float, size_mb: float):
            from src.clubbot.services.transcript.types import AudioChunk

            return [
                AudioChunk(path="c1", start_seconds=0.0, duration_seconds=60.0, size_bytes=10),
                AudioChunk(path="c2", start_seconds=60.0, duration_seconds=60.0, size_bytes=10),
            ]

    monkeypatch.setattr(stt_mod, "AudioChunker", _FakeChunker, raising=True)

    created: dict[str, int] = {}

    class _FakePT:
        def __init__(self, *, max_retries: int, **_: object) -> None:
            created["max_retries"] = max_retries

        def transcribe_chunks(self, chunks):
            from src.clubbot.services.transcript.types import TranscriptSegment

            return [
                [TranscriptSegment(text="a", start=0.0, duration=1.0)],
                [TranscriptSegment(text="b", start=0.0, duration=1.0)],
            ]

    monkeypatch.setattr(stt_mod, "ParallelTranscriber", _FakePT, raising=True)
    monkeypatch.setattr(
        stt_mod,
        "TranscriptMerger",
        lambda: SimpleNamespace(merge=lambda pairs: []),
        raising=True,
    )

    # Create dummy file path
    fd, path = __import__("tempfile").mkstemp(prefix="orig_", suffix=".m4a")
    __import__("os").close(fd)
    _ = p._transcribe_chunked(path)
    assert created.get("max_retries") == p.max_retries
