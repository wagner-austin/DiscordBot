from __future__ import annotations

import base64
import os
import tempfile
from types import SimpleNamespace
from typing import Any

import pytest
import src.clubbot.services.transcript.stt_provider as stt_mod
from src.clubbot.services.transcript.stt_provider import STTTranscriptProvider
from src.clubbot.services.transcript.types import TranscriptSegment
from src.clubbot.utils.errors import UserInputError


class _FakeOpenAI:
    def __init__(self, *args: object, **kwargs: object) -> None:
        self.audio = SimpleNamespace(transcriptions=SimpleNamespace(create=lambda **_: None))


def _patch_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(__import__("sys").modules, "openai", SimpleNamespace(OpenAI=_FakeOpenAI))


def test_probe_uses_cookiefile_from_cookies_text(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_openai(monkeypatch)

    # Prepare yt_dlp fake that captures options
    captured_opts: dict[str, Any] = {}

    class _YDL:
        def __init__(self, opts: dict[str, Any]) -> None:
            nonlocal captured_opts
            captured_opts = dict(opts)

        def __enter__(self) -> _YDL:
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def extract_info(self, url: str, download: bool = False) -> dict[str, object]:
            assert download is False
            return {"duration": 60}

    monkeypatch.setitem(__import__("sys").modules, "yt_dlp", SimpleNamespace(YoutubeDL=_YDL))

    # Provide cookies via text -> temp file
    text = base64.b64encode(b"dummy-cookies").decode("ascii")
    p = STTTranscriptProvider(
        api_key="x",
        max_video_seconds=9999,
        max_file_mb=25,
        cookies_text=text,
        enable_chunking=False,
    )

    info = p._probe("https://youtu.be/vid")
    assert isinstance(info, dict) and info.get("duration") == 60
    assert "cookiefile" in captured_opts
    cookie_path = captured_opts["cookiefile"]
    assert isinstance(cookie_path, str) and os.path.isfile(cookie_path)


def test_download_audio_uses_cookiefile_when_path_provided(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_openai(monkeypatch)

    # Prepare output file
    outdir = tempfile.mkdtemp(prefix="ydl_")
    outfile = os.path.join(outdir, "audio.m4a")
    with open(outfile, "wb") as f:
        f.write(b"data")

    captured_opts: dict[str, Any] = {}

    class _YDL:
        def __init__(self, opts: dict[str, Any]) -> None:
            nonlocal captured_opts
            captured_opts = dict(opts)

        def __enter__(self) -> _YDL:
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def extract_info(self, url: str, download: bool = True) -> dict[str, object]:
            assert download is True
            # Simulate requested_downloads to a file we prepared
            return {"requested_downloads": [{"filepath": outfile}]}

        def prepare_filename(self, info: dict[str, object]) -> str:
            return outfile

    monkeypatch.setitem(__import__("sys").modules, "yt_dlp", SimpleNamespace(YoutubeDL=_YDL))

    p = STTTranscriptProvider(
        api_key="x",
        max_video_seconds=9999,
        max_file_mb=25,
        cookies_path="/tmp/cookies.txt",
        enable_chunking=False,
    )

    path = p._download_audio("https://youtu.be/vid")
    assert path == outfile
    assert "cookiefile" in captured_opts and captured_opts["cookiefile"] == "/tmp/cookies.txt"


def test_handle_over_limit_with_chunking_calls_chunked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_openai(monkeypatch)
    p = STTTranscriptProvider(
        api_key="x",
        max_video_seconds=9999,
        max_file_mb=1,
        enable_chunking=True,
    )
    monkeypatch.setattr(p, "_ffmpeg_available", lambda: True, raising=True)
    called: dict[str, int] = {"n": 0}

    def fake_chunked(path: str) -> list[TranscriptSegment]:
        called["n"] += 1
        return [TranscriptSegment(text="t", start=0.0, duration=1.0)]

    monkeypatch.setattr(p, "_transcribe_chunked", fake_chunked, raising=True)
    res = p._handle_over_limit("/tmp/a.m4a", size_bytes=5 * 1024 * 1024)
    assert called["n"] == 1 and res and res[0].text == "t"


def test_handle_over_limit_without_chunking_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_openai(monkeypatch)
    p = STTTranscriptProvider(
        api_key="x",
        max_video_seconds=9999,
        max_file_mb=1,
        enable_chunking=False,
    )
    with pytest.raises(UserInputError):
        _ = p._handle_over_limit("/tmp/a.m4a", size_bytes=5 * 1024 * 1024)


def test_transcribe_with_strategy_uses_chunked_when_should(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_openai(monkeypatch)
    # Create small temp audio file
    fd, path = tempfile.mkstemp(prefix="stt_", suffix=".m4a")
    os.close(fd)

    p = STTTranscriptProvider(
        api_key="x",
        max_video_seconds=9999,
        max_file_mb=25,
        enable_chunking=True,
    )
    monkeypatch.setattr(p, "_should_chunk", lambda _: True, raising=True)
    monkeypatch.setattr(
        p,
        "_transcribe_chunked",
        lambda _: [TranscriptSegment(text="ok", start=0.0, duration=1.0)],
        raising=True,
    )
    res = p._transcribe_with_strategy(path)
    assert res and res[0].text == "ok"


def test_transcribe_with_strategy_maps_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_openai(monkeypatch)
    fd, path = tempfile.mkstemp(prefix="stt_", suffix=".m4a")
    os.close(fd)

    p = STTTranscriptProvider(
        api_key="x",
        max_video_seconds=9999,
        max_file_mb=25,
        enable_chunking=False,
    )

    def _raise_transcribe(_: str) -> list[TranscriptSegment]:
        raise ValueError("boom")

    monkeypatch.setattr(p, "_transcribe", _raise_transcribe, raising=True)
    with pytest.raises(UserInputError):
        _ = p._transcribe_with_strategy(path)


def test_download_or_error_maps_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_openai(monkeypatch)
    p = STTTranscriptProvider(api_key="x", max_video_seconds=9999, max_file_mb=25)

    def _raise_download(_: str) -> str:
        raise OSError("x")

    monkeypatch.setattr(p, "_download_audio", _raise_download, raising=True)
    with pytest.raises(UserInputError):
        _ = p._download_or_error("https://youtu.be/vid", "vid")


def test_estimate_uses_formats_and_abr(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_openai(monkeypatch)
    p = STTTranscriptProvider(api_key="x", max_video_seconds=9999, max_file_mb=25)

    def fake_probe(url: str) -> dict[str, object]:
        return {
            "duration": 120,
            "formats": [
                {"vcodec": "none", "acodec": "aac", "filesize": 2 * 1024 * 1024},
                {"vcodec": "none", "acodec": "aac", "abr": 128},  # kbps
            ],
        }

    monkeypatch.setattr(p, "_probe", fake_probe, raising=True)
    duration, approx_mb = p.estimate("https://youtu.be/vid")
    # Prefers explicit size (2 MiB); duration is from probe
    assert duration == 120 and 1.9 <= approx_mb <= 2.1


def test_get_audio_duration_timeout_and_bad_json(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_openai(monkeypatch)
    p = STTTranscriptProvider(api_key="x", max_video_seconds=9999, max_file_mb=25)

    import subprocess

    def raise_timeout(*args: object, **kwargs: object) -> None:
        raise subprocess.TimeoutExpired(cmd="ffprobe", timeout=30)

    monkeypatch.setattr(subprocess, "run", raise_timeout, raising=True)
    assert p._get_audio_duration("/tmp/a.m4a") == 0.0

    def ok_but_bad_json(*args: object, **kwargs: object):
        return SimpleNamespace(stdout="{]", stderr="")

    monkeypatch.setattr(subprocess, "run", ok_but_bad_json, raising=True)
    assert p._get_audio_duration("/tmp/a.m4a") == 0.0


def test_should_chunk_returns_false_on_oserror(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_openai(monkeypatch)
    p = STTTranscriptProvider(
        api_key="x",
        max_video_seconds=9999,
        max_file_mb=25,
        enable_chunking=True,
    )

    def raise_oserror(_path: str) -> int:
        raise OSError("stat failed")

    monkeypatch.setattr(__import__("os").path, "getsize", raise_oserror, raising=True)
    assert p._should_chunk("/tmp/a.m4a") is False


def test_transcribe_chunked_cleans_up_and_merges(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: str = "",
) -> None:
    _patch_openai(monkeypatch)
    p = STTTranscriptProvider(
        api_key="x",
        max_video_seconds=9999,
        max_file_mb=1,
        enable_chunking=True,
    )
    monkeypatch.setattr(p, "_ffmpeg_available", lambda: True, raising=True)
    monkeypatch.setattr(p, "_get_audio_duration", lambda _p: 120.0, raising=True)
    monkeypatch.setattr(__import__("os").path, "getsize", lambda _p: 50 * 1024 * 1024, raising=True)

    # Create original audio file
    fd, orig = tempfile.mkstemp(prefix="orig_", suffix=".m4a")
    os.close(fd)
    with open(orig, "wb") as f:
        f.write(b"data")

    # Prepare chunk files to be cleaned up
    c1_fd, c1 = tempfile.mkstemp(prefix="chunk_", suffix=".m4a")
    c2_fd, c2 = tempfile.mkstemp(prefix="chunk_", suffix=".m4a")
    os.close(c1_fd)
    os.close(c2_fd)

    # Fake AudioChunker that returns our chunk files
    class _FakeChunker:
        def __init__(self, *a: object, **k: object) -> None:
            pass

        def chunk_audio(self, path: str, duration: float, size_mb: float):
            from src.clubbot.services.transcript.types import AudioChunk

            return [
                AudioChunk(path=c1, start_seconds=0.0, duration_seconds=60.0, size_bytes=10),
                AudioChunk(path=c2, start_seconds=60.0, duration_seconds=60.0, size_bytes=10),
            ]

    monkeypatch.setattr(stt_mod, "AudioChunker", _FakeChunker, raising=True)

    # Fake ParallelTranscriber that returns segments for each chunk
    class _FakePT:
        def __init__(self, *a: object, **k: object) -> None:
            pass

        def transcribe_chunks(self, chunks):
            from src.clubbot.services.transcript.types import TranscriptSegment

            return [
                [TranscriptSegment(text="a", start=0.0, duration=1.0)],
                [TranscriptSegment(text="b", start=0.0, duration=1.0)],
            ]

    monkeypatch.setattr(stt_mod, "ParallelTranscriber", _FakePT, raising=True)

    # Fake merger that joins segments
    class _FakeMerger:
        def merge(self, pairs):
            from src.clubbot.services.transcript.types import TranscriptSegment

            return [
                TranscriptSegment(text="a", start=0.0, duration=1.0),
                TranscriptSegment(text="b", start=0.0, duration=1.0),
            ]

    monkeypatch.setattr(stt_mod, "TranscriptMerger", _FakeMerger, raising=True)

    out = p._transcribe_chunked(orig)
    assert len(out) == 2 and out[0].text == "a" and out[1].text == "b"
    # Chunk files cleaned up; original remains
    assert not os.path.exists(c1) and not os.path.exists(c2) and os.path.exists(orig)


def test_transcribe_chunked_passthrough_calls_transcribe(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_openai(monkeypatch)
    p = STTTranscriptProvider(
        api_key="x",
        max_video_seconds=9999,
        max_file_mb=25,
        enable_chunking=True,
    )
    monkeypatch.setattr(p, "_ffmpeg_available", lambda: True, raising=True)
    monkeypatch.setattr(p, "_get_audio_duration", lambda _p: 10.0, raising=True)
    called = {"n": 0}

    def fake_transcribe(_: str):
        called["n"] += 1
        return [TranscriptSegment(text="ok", start=0.0, duration=1.0)]

    from src.clubbot.services.transcript.types import AudioChunk, TranscriptSegment

    class _FakeChunker:
        def __init__(self, *a: object, **k: object) -> None:
            pass

        def chunk_audio(self, audio_path: str, duration: float, size_mb: float):
            return [
                AudioChunk(
                    path=audio_path,
                    start_seconds=0.0,
                    duration_seconds=duration,
                    size_bytes=10,
                )
            ]

    monkeypatch.setattr(stt_mod, "AudioChunker", _FakeChunker, raising=True)
    monkeypatch.setattr(p, "_transcribe", fake_transcribe, raising=True)
    fd, orig = tempfile.mkstemp(prefix="orig_", suffix=".m4a")
    os.close(fd)
    out = p._transcribe_chunked(orig)
    assert called["n"] == 1 and out and out[0].text == "ok"


def test_probe_or_error_maps_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_openai(monkeypatch)
    p = STTTranscriptProvider(api_key="x", max_video_seconds=9999, max_file_mb=25)

    def bad_probe(url: str) -> dict[str, object]:
        raise ValueError("probe failed")

    monkeypatch.setattr(p, "_probe", bad_probe, raising=True)
    with pytest.raises(UserInputError):
        _ = p._probe_or_error("vid", "https://youtu.be/vid")


def test_download_or_error_stats_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_openai(monkeypatch)
    p = STTTranscriptProvider(api_key="x", max_video_seconds=9999, max_file_mb=25)

    fd, path = tempfile.mkstemp(prefix="aud_", suffix=".m4a")
    os.close(fd)

    monkeypatch.setattr(p, "_download_audio", lambda url: path, raising=True)
    # First stat raises; second returns real stat
    calls = {"n": 0}
    orig_stat = stt_mod.os.stat

    def flaky_stat(pth: str, *args: object, **kwargs: object):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("stat failed")
        return orig_stat(pth, *args, **kwargs)

    monkeypatch.setattr(stt_mod.os, "stat", flaky_stat, raising=True)
    out_path, size = p._download_or_error("https://youtu.be/vid", "vid")
    assert out_path == path and size >= 0 and calls["n"] >= 2
