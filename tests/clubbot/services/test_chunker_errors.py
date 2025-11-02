from __future__ import annotations

import os
import tempfile
from types import SimpleNamespace

import pytest
from src.clubbot.services.transcript.chunker import AudioChunker


def test_detect_silence_timeout_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    ch = AudioChunker()
    import subprocess

    def raise_timeout(*args: object, **kwargs: object) -> None:
        raise subprocess.TimeoutExpired(cmd="ffmpeg", timeout=90)

    monkeypatch.setattr(subprocess, "run", raise_timeout, raising=True)
    assert ch._detect_silence("/tmp/a.m4a", 10.0) == []


def test_split_audio_copy_timeout_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    ch = AudioChunker()
    monkeypatch.setattr(ch, "_probe_stream_info", lambda p: ("m4a", "aac"), raising=True)

    # Create dummy input file
    fd, in_path = tempfile.mkstemp(prefix="aud_", suffix=".m4a")
    os.close(fd)

    import subprocess

    def raise_timeout(*args: object, **kwargs: object) -> None:
        raise subprocess.TimeoutExpired(cmd="ffmpeg", timeout=90)

    monkeypatch.setattr(subprocess, "run", raise_timeout, raising=True)

    with pytest.raises(__import__("subprocess").TimeoutExpired):
        _ = ch._split_audio(in_path, [1.0], total_duration=2.0)


def test_split_audio_reencode_timeout_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    ch = AudioChunker()
    monkeypatch.setattr(ch, "_probe_stream_info", lambda p: ("m4a", "aac"), raising=True)

    fd, in_path = tempfile.mkstemp(prefix="aud_", suffix=".m4a")
    os.close(fd)

    calls = {"n": 0}
    import subprocess

    def run_with_fallback(cmd, check=False, capture_output=False, text=False, timeout=None):
        if "-c:a" in cmd:
            # Simulate reencode path timing out
            raise subprocess.TimeoutExpired(cmd="ffmpeg", timeout=120)
        # First call (copy) fails to trigger fallback
        calls["n"] += 1
        raise subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr(subprocess, "run", run_with_fallback, raising=True)

    with pytest.raises(__import__("subprocess").TimeoutExpired):
        _ = ch._split_audio(in_path, [1.0], total_duration=2.0)
    assert calls["n"] == 1


def test_probe_stream_info_timeout_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    ch = AudioChunker()
    import subprocess

    def raise_timeout(*args: object, **kwargs: object) -> None:
        raise subprocess.TimeoutExpired(cmd="ffprobe", timeout=30)

    monkeypatch.setattr(subprocess, "run", raise_timeout, raising=True)
    container, codec = ch._probe_stream_info("/tmp/a.m4a")
    assert container == "" and codec == ""


def test_probe_stream_info_bad_json_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    ch = AudioChunker()
    import subprocess

    def bad_json(*args: object, **kwargs: object):
        return SimpleNamespace(stdout="not json", stderr="")

    monkeypatch.setattr(subprocess, "run", bad_json, raising=True)
    container, codec = ch._probe_stream_info("/tmp/a.m4a")
    assert container == "" and codec == ""

    # _get_audio_duration is implemented in STTTranscriptProvider; see stt_provider_advanced tests
    pass
