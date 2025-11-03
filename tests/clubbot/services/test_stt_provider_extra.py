from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any, BinaryIO, Literal

import pytest
import src.clubbot.services.transcript.stt_provider as stt_mod
from src.clubbot.services.transcript.stt_provider import STTTranscriptProvider
from src.clubbot.services.transcript.types import TranscriptSegment
from src.clubbot.utils.errors import UserInputError


def _patch_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Client:
        def __init__(self, *_: object, **__: object) -> None:
            self.audio = SimpleNamespace(
                transcriptions=SimpleNamespace(create=lambda **kwargs: SimpleNamespace(**kwargs))
            )

    monkeypatch.setitem(__import__("sys").modules, "openai", SimpleNamespace(OpenAI=_Client))


def test_transcribe_invokes_convert_verbose(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_openai(monkeypatch)
    p = STTTranscriptProvider(api_key="x", max_video_seconds=9999, max_file_mb=25)

    called: dict[str, Any] = {}

    def fake_convert(resp: object) -> list[TranscriptSegment]:
        called["resp"] = resp
        return [TranscriptSegment(text="ok", start=0.0, duration=1.0)]

    monkeypatch.setattr(stt_mod, "convert_verbose_to_segments", fake_convert, raising=True)

    fd, path = tempfile.mkstemp(prefix="aud_", suffix=".m4a")
    os.close(fd)
    try:
        out = p._transcribe(path)
        assert out and out[0].text == "ok"
        assert "resp" in called
    finally:
        with __import__("contextlib").suppress(Exception):
            os.remove(path)


def test_ffmpeg_available_checks_binaries(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_openai(monkeypatch)
    p = STTTranscriptProvider(api_key="x", max_video_seconds=1, max_file_mb=1)

    def _which(name: str) -> str | None:
        return "x" if name in {"ffmpeg", "ffprobe"} else None

    monkeypatch.setattr(shutil, "which", _which)
    assert p._ffmpeg_available() is True

    monkeypatch.setattr(shutil, "which", lambda name: None)
    assert p._ffmpeg_available() is False


def test_should_chunk_threshold_and_oserror(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_openai(monkeypatch)
    p = STTTranscriptProvider(api_key="x", max_video_seconds=1, max_file_mb=1, enable_chunking=True)
    fd, path = tempfile.mkstemp(prefix="aud_", suffix=".m4a")
    os.close(fd)
    try:

        def big_size(_: str) -> int:
            return int((p.chunk_threshold_mb + 5) * 1024 * 1024)

        monkeypatch.setattr(os.path, "getsize", big_size)
        assert p._should_chunk(path) is True

        def raise_oserror(_: str) -> int:
            raise OSError("fail")

        monkeypatch.setattr(os.path, "getsize", raise_oserror)
        assert p._should_chunk(path) is False
    finally:
        with __import__("contextlib").suppress(Exception):
            os.remove(path)


def test_get_audio_duration_parse_and_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_openai(monkeypatch)
    p = STTTranscriptProvider(api_key="x", max_video_seconds=1, max_file_mb=1)
    fd, path = tempfile.mkstemp(prefix="aud_", suffix=".m4a")
    os.close(fd)
    try:
        payload = {"format": {"duration": "12.5"}}
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *a, **k: SimpleNamespace(stdout=json.dumps(payload), stderr=""),
            raising=True,
        )
        assert p._get_audio_duration(path) == 12.5

        def raise_to(*_: object, **__: object) -> None:
            raise subprocess.TimeoutExpired(cmd="ffprobe", timeout=1)

        monkeypatch.setattr(subprocess, "run", raise_to, raising=True)
        assert p._get_audio_duration(path) == 0.0
    finally:
        with __import__("contextlib").suppress(Exception):
            os.remove(path)


def test_transcribe_with_strategy_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_openai(monkeypatch)
    p = STTTranscriptProvider(api_key="x", max_video_seconds=1, max_file_mb=1, enable_chunking=True)
    fd, path = tempfile.mkstemp(prefix="a_", suffix=".m4a")
    os.close(fd)
    try:
        monkeypatch.setattr(p, "_should_chunk", lambda _p: True, raising=True)

        def ret_chunked(_: str) -> list[TranscriptSegment]:
            return [TranscriptSegment("t", 0.0, 1.0)]

        monkeypatch.setattr(p, "_transcribe_chunked", ret_chunked, raising=True)
        out = p._transcribe_with_strategy(path)
        assert out and out[0].text == "t"

        def raise_err(_: str) -> list[TranscriptSegment]:
            raise RuntimeError("boom")

        monkeypatch.setattr(p, "_should_chunk", lambda _p: False, raising=True)
        monkeypatch.setattr(p, "_transcribe", raise_err, raising=True)
        with pytest.raises(UserInputError):
            p._transcribe_with_strategy(path)
    finally:
        with __import__("contextlib").suppress(Exception):
            os.remove(path)


def test_handle_over_limit_chunked_failure_maps(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_openai(monkeypatch)
    p = STTTranscriptProvider(
        api_key="x",
        max_video_seconds=1,
        max_file_mb=1,
        enable_chunking=True,
    )
    monkeypatch.setattr(p, "_ffmpeg_available", lambda: True, raising=True)

    def raise_chunk(_: str) -> list[TranscriptSegment]:
        raise ValueError("x")

    monkeypatch.setattr(p, "_transcribe_chunked", raise_chunk, raising=True)
    with pytest.raises(UserInputError):
        p._handle_over_limit("/tmp/a.m4a", 10 * 1024 * 1024)


def test_probe_returns_non_dict_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_openai(monkeypatch)

    class _YDL:
        def __init__(self, *_: object, **__: object) -> None:
            pass

        def __enter__(self) -> _YDL:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def extract_info(self, url: str, download: bool = False) -> object:
            return 123

    monkeypatch.setitem(__import__("sys").modules, "yt_dlp", SimpleNamespace(YoutubeDL=_YDL))
    p = STTTranscriptProvider(api_key="x", max_video_seconds=1, max_file_mb=1)
    with pytest.raises(UserInputError):
        _ = p._probe("https://youtu.be/vid")


def test_download_audio_missing_path_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_openai(monkeypatch)
    outdir = tempfile.mkdtemp(prefix="ydl_")
    missing = os.path.join(outdir, "missing.m4a")

    class _YDL:
        def __init__(self, *_: object, **__: object) -> None:
            pass

        def __enter__(self) -> _YDL:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def extract_info(self, url: str, download: bool = True) -> dict[str, object]:
            return {"requested_downloads": [{"filepath": missing}]}

        def prepare_filename(self, info: dict[str, object]) -> str:
            return missing

    monkeypatch.setitem(__import__("sys").modules, "yt_dlp", SimpleNamespace(YoutubeDL=_YDL))
    p = STTTranscriptProvider(api_key="x", max_video_seconds=1, max_file_mb=1)
    with pytest.raises(UserInputError):
        _ = p._download_audio("https://youtu.be/vid")


def test_download_audio_prepare_filename_empty_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_openai(monkeypatch)
    p = STTTranscriptProvider(api_key="x", max_video_seconds=1, max_file_mb=1)

    class _YDL2:
        def __init__(self, *_: object, **__: object) -> None:
            pass

        def __enter__(self) -> _YDL2:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def extract_info(self, url: str, download: bool = True) -> dict[str, object]:
            return {"requested_downloads": []}

        def prepare_filename(self, info: dict[str, object]) -> str:
            return ""

    monkeypatch.setitem(__import__("sys").modules, "yt_dlp", SimpleNamespace(YoutubeDL=_YDL2))
    with pytest.raises(UserInputError):
        _ = p._download_audio("https://youtu.be/vid")


def test_estimate_loop_cover(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_openai(monkeypatch)
    p = STTTranscriptProvider(api_key="x", max_video_seconds=1, max_file_mb=1)
    fmts2 = [
        {"vcodec": "", "acodec": "aac", "abr": "96", "filesize_approx": 0},
    ]
    monkeypatch.setattr(p, "_probe", lambda url: {"duration": 30, "formats": fmts2}, raising=True)
    dur3, mb3 = p.estimate("https://youtu.be/x")
    assert dur3 == 30 and mb3 >= 0.0


def test_estimate_formats_and_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_openai(monkeypatch)
    p = STTTranscriptProvider(api_key="x", max_video_seconds=1, max_file_mb=1)

    fmts = [
        {"vcodec": "none", "acodec": "mp4a.40.2", "abr": 128, "filesize": 5 * 1024 * 1024},
        {"vcodec": "none", "acodec": "opus", "abr": 256},
        {"vcodec": "h264", "acodec": "none"},
    ]
    monkeypatch.setattr(p, "_probe", lambda url: {"duration": 60, "formats": fmts}, raising=True)
    dur, mb = p.estimate("https://youtu.be/x")
    assert dur == 60 and mb >= 5.0

    # fallback via abr only
    def _probe_fallback(_: str) -> dict[str, object]:
        return {"duration": 60, "formats": [{"vcodec": "none", "acodec": "opus", "abr": 64}]}

    monkeypatch.setattr(p, "_probe", _probe_fallback, raising=True)
    dur2, mb2 = p.estimate("https://youtu.be/x")
    assert dur2 == 60 and mb2 > 0.0


def test_estimate_eta_chunked_and_non_chunked(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_openai(monkeypatch)
    p = STTTranscriptProvider(
        api_key="x",
        max_video_seconds=1,
        max_file_mb=5,
        enable_chunking=True,
        stt_rtf=0.5,
        dl_mib_per_sec=5.0,
        target_chunk_mb=2.0,
        max_chunk_duration=60.0,
        max_concurrent_chunks=2,
    )
    monkeypatch.setattr(p, "_ffmpeg_available", lambda: True, raising=True)

    # Non-chunk path
    m1 = p.estimate_eta_minutes(duration_seconds=120, approx_size_mb=1.0)
    assert m1 >= 1

    # Chunk path
    m2 = p.estimate_eta_minutes(duration_seconds=240, approx_size_mb=10.0)
    assert m2 >= 1 and m2 <= m1 + 10


def test_del_removes_temp_cookie_file(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_openai(monkeypatch)
    text = __import__("base64").b64encode(b"cookies").decode("ascii")
    p = STTTranscriptProvider(api_key="x", max_video_seconds=1, max_file_mb=1, cookies_text=text)
    path = getattr(p, "_temp_cookies_file", None)
    assert isinstance(path, str) and os.path.isfile(path)
    # Explicitly invoke destructor to ensure cleanup is covered
    p.__del__()
    assert not os.path.exists(path)


def test_transcribe_with_strategy_oserror_path(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_openai(monkeypatch)
    p = STTTranscriptProvider(api_key="x", max_video_seconds=1, max_file_mb=1)
    fd, path = tempfile.mkstemp(prefix="a_", suffix=".m4a")
    os.close(fd)
    try:

        def raise_os(_: str) -> int:
            raise OSError("getsize failed")

        monkeypatch.setattr(os.path, "getsize", raise_os)

        def ret_single(_: str) -> list[TranscriptSegment]:
            return [TranscriptSegment("s", 0.0, 1.0)]

        monkeypatch.setattr(p, "_transcribe", ret_single, raising=True)
        out = p._transcribe_with_strategy(path)
        assert out and out[0].text == "s"
    finally:
        with __import__("contextlib").suppress(Exception):
            os.remove(path)


def test_is_over_limit_variants(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_openai(monkeypatch)
    p0 = STTTranscriptProvider(api_key="x", max_video_seconds=1, max_file_mb=0)
    assert p0._is_over_limit(10) is False
    p = STTTranscriptProvider(api_key="x", max_video_seconds=1, max_file_mb=1)
    assert p._is_over_limit(0) is False
    assert p._is_over_limit(2 * 1024 * 1024) is True


def test_parallel_calls_inner_transcribe(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_openai(monkeypatch)
    p = STTTranscriptProvider(api_key="x", max_video_seconds=1, max_file_mb=1, enable_chunking=True)
    monkeypatch.setattr(p, "_ffmpeg_available", lambda: True, raising=True)
    monkeypatch.setattr(p, "_get_audio_duration", lambda _p: 10.0, raising=True)

    # Fake chunker producing two distinct chunk paths
    class _FakeChunker:
        def __init__(self, *a: object, **k: object) -> None:
            pass

        def chunk_audio(self, path: str, duration: float, size_mb: float):
            from src.clubbot.services.transcript.types import AudioChunk

            c1_fd, c1 = tempfile.mkstemp(prefix="c1_", suffix=".m4a")
            c2_fd, c2 = tempfile.mkstemp(prefix="c2_", suffix=".m4a")
            os.close(c1_fd)
            os.close(c2_fd)
            return [
                AudioChunk(path=c1, start_seconds=0.0, duration_seconds=5.0, size_bytes=10),
                AudioChunk(path=c2, start_seconds=5.0, duration_seconds=5.0, size_bytes=10),
            ]

    monkeypatch.setattr(stt_mod, "AudioChunker", _FakeChunker, raising=True)

    invoked: dict[str, int] = {"n": 0}

    class _FakePT:
        def __init__(
            self,
            *,
            transcribe: Callable[[str, BinaryIO, Literal["verbose_json"], float | None], object],
            **_: object,
        ) -> None:
            # Call the provided transcribe once to exercise the inner function
            bio = __import__("io").BytesIO(b"x")
            transcribe(model="whisper-1", file=bio, response_format="verbose_json", timeout=1.0)
            invoked["n"] += 1

        def transcribe_chunks(self, chunks: object) -> list[list[TranscriptSegment]]:
            from src.clubbot.services.transcript.types import TranscriptSegment

            return [
                [TranscriptSegment(text="x", start=0.0, duration=1.0)],
                [TranscriptSegment(text="y", start=0.0, duration=1.0)],
            ]

    monkeypatch.setattr(stt_mod, "ParallelTranscriber", _FakePT, raising=True)
    monkeypatch.setattr(
        stt_mod, "TranscriptMerger", lambda: SimpleNamespace(merge=lambda pairs: [])
    )

    fd, orig = tempfile.mkstemp(prefix="orig_", suffix=".m4a")
    os.close(fd)
    try:
        _ = p._transcribe_chunked(orig)
        assert invoked["n"] == 1
    finally:
        with __import__("contextlib").suppress(Exception):
            os.remove(orig)


def test_as_float_edge_cases() -> None:
    assert stt_mod._as_float(5) == 5.0
    assert stt_mod._as_float(3.5) == 3.5
    assert stt_mod._as_float("7.25") == 7.25
    assert stt_mod._as_float("x") == 0.0
    assert stt_mod._as_float(object()) == 0.0
