from __future__ import annotations

import os
import subprocess
import tempfile

import pytest
from src.clubbot.services.transcript.chunker import AudioChunker


def _fake_run_ok(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
    # Simulate successful ffmpeg/ffprobe call without creating files
    return subprocess.CompletedProcess(args=["ffmpeg"], returncode=0, stdout="", stderr="")


def test_chunker_selects_webm_for_opus(monkeypatch: pytest.MonkeyPatch) -> None:
    ch = AudioChunker()
    # Force opus codec so we expect webm extension
    monkeypatch.setattr(ch, "_probe_stream_info", lambda p: ("matroska,webm", "opus"))
    monkeypatch.setattr(ch, "_detect_silence", lambda p, d: [])
    # Avoid invoking real ffmpeg
    monkeypatch.setattr("subprocess.run", _fake_run_ok)
    # Use a temp file path for input (size doesn't matter since we pass estimated_mb)
    fd, audio_path = tempfile.mkstemp(prefix="chunker_in_", suffix=".webm")
    os.close(fd)
    try:
        chunks = ch.chunk_audio(audio_path, total_duration=60.0, estimated_mb=100.0)
    finally:
        with __import__("contextlib").suppress(Exception):
            os.remove(audio_path)
    # Expect 5 chunks (ceil(100/20)) and .webm extension
    assert len(chunks) == 5
    assert all(c.path.endswith(".webm") for c in chunks)


def test_chunker_selects_m4a_for_aac(monkeypatch: pytest.MonkeyPatch) -> None:
    ch = AudioChunker()
    # Force aac codec so we expect m4a extension
    monkeypatch.setattr(ch, "_probe_stream_info", lambda p: ("mp4", "aac"))
    monkeypatch.setattr(ch, "_detect_silence", lambda p, d: [])
    monkeypatch.setattr("subprocess.run", _fake_run_ok)
    fd, audio_path = tempfile.mkstemp(prefix="chunker_in_", suffix=".m4a")
    os.close(fd)
    try:
        chunks = ch.chunk_audio(audio_path, total_duration=60.0, estimated_mb=60.0)
    finally:
        with __import__("contextlib").suppress(Exception):
            os.remove(audio_path)
    # Expect 3 chunks (ceil(60/20)) and .m4a extension
    assert len(chunks) == 3
    assert all(c.path.endswith(".m4a") for c in chunks)
