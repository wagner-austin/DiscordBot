from __future__ import annotations

import json
import os
import tempfile
from contextlib import suppress
from types import SimpleNamespace

import pytest
from src.clubbot.services.transcript.chunker import AudioChunker


def _touch(path: str, size: int = 0) -> None:
    with open(path, "wb") as f:
        f.write(b"x" * size)


def test_chunker_passthrough_when_below_threshold(tmp_path: str = "") -> None:
    fd, path = tempfile.mkstemp(prefix="aud_", suffix=".m4a")
    os.close(fd)
    _touch(path, size=1024)
    ch = AudioChunker(target_chunk_mb=10.0, max_chunk_duration_seconds=600.0)
    chunks = ch.chunk_audio(path, total_duration=30.0, estimated_mb=0.5)
    assert len(chunks) == 1 and os.path.abspath(chunks[0].path) == os.path.abspath(path)


def test_detect_silence_parses_ffmpeg_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ch = AudioChunker()
    sample = "\n".join(
        [
            "silence_start: 1.0",
            "silence_end: 2.50 | silence_duration: 1.50",
            "silence_end: 4.00 | silence_duration: 0.50",
        ]
    )
    monkeypatch.setattr(
        __import__("subprocess"),
        "run",
        lambda *a, **k: SimpleNamespace(stdout=sample, stderr=""),
        raising=True,
    )
    points = ch._detect_silence("/tmp/a.m4a", 10.0)
    assert points == [2.5, 4.0]


def test_split_audio_copy_then_reencode(monkeypatch: pytest.MonkeyPatch) -> None:
    ch = AudioChunker()
    # Force codec to opus to pick webm; then fallback re-encode for second segment
    monkeypatch.setattr(ch, "_probe_stream_info", lambda p: ("webm", "opus"))

    # Create dummy input file
    fd, in_path = tempfile.mkstemp(prefix="aud_", suffix=".webm")
    os.close(fd)
    _touch(in_path, size=2048)

    calls: list[str] = []

    def fake_run(cmd, check=False, capture_output=False, text=False, timeout=None):
        nonlocal calls
        # When re-encode, we see '-c:a' in cmd
        if "-c:a" in cmd:
            calls.append("reencode")
        else:
            # First call (copy) fails to trigger fallback
            calls.append("copy")
            raise __import__("subprocess").CalledProcessError(1, cmd)
        # Create the output file referenced by last arg
        out_path = cmd[-1]
        _touch(out_path, size=512)
        return SimpleNamespace(stdout="", stderr="")

    monkeypatch.setattr(__import__("subprocess"), "run", fake_run, raising=True)

    # Two segments from 0-1 and 1-2 seconds to force two chunks
    created = ch._split_audio(in_path, [1.0], total_duration=2.0)
    # Expect two chunks, with at least one copy attempt and one re-encode fallback
    assert len(created) == 2
    assert calls and calls[0] == "copy"
    assert "reencode" in calls
    with suppress(Exception):
        os.remove(in_path)


def test_probe_stream_info_parses_json(monkeypatch: pytest.MonkeyPatch) -> None:
    ch = AudioChunker()
    payload = {
        "format": {"format_name": "m4a", "format_long_name": "MPEG-4 AAC"},
        "streams": [
            {"codec_type": "video", "codec_name": "h264"},
            {"codec_type": "audio", "codec_name": "aac"},
        ],
    }
    monkeypatch.setattr(
        __import__("subprocess"),
        "run",
        lambda *a, **k: SimpleNamespace(stdout=json.dumps(payload), stderr=""),
        raising=True,
    )
    container, codec = ch._probe_stream_info("/tmp/a.m4a")
    assert container == "m4a" and codec == "aac"
