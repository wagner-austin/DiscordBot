from __future__ import annotations

from pathlib import Path

import pytest
from src.clubbot.services.transcript.chunker import AudioChunker


def _make_tmp_audio(tmp_path: Path) -> str:
    p = tmp_path / "audio.m4a"
    p.write_bytes(b"data")
    return str(p)


def test_calculate_split_points_ideal_empty_returns_empty() -> None:
    c = AudioChunker(target_chunk_mb=20.0)
    # estimated_mb small enough to result in num_chunks == 1 => ideal empty => []
    out = c._calculate_split_points([], total_duration=30.0, estimated_mb=5.0)
    assert out == []


def test_split_audio_clamps_points_and_copy_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = AudioChunker()
    audio = _make_tmp_audio(tmp_path)

    # Pretend probe found non-opus codec (m4a)
    monkeypatch.setattr(c, "_probe_stream_info", lambda _p: ("mp4", "aac"))

    def _fake_run(
        cmd: list[str],
        check: bool = False,
        capture_output: bool = False,
        text: bool = False,
        timeout: object | None = None,
    ) -> object:
        # Create the output file to satisfy os.path.getsize
        out_path = cmd[-1]
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_bytes(b"x")

        class _R:
            stdout = ""
            stderr = ""
            returncode = 0

        return _R()

    import subprocess as _sp

    monkeypatch.setattr(_sp, "run", _fake_run)
    # Provide out-of-range split points to exercise clamping
    created = c._split_audio(audio, split_points=[-5.0, 9999.0], total_duration=3.0)
    assert created and all(0.0 <= seg.start_seconds <= 3.0 for seg in created)


def test_cleanup_dir_nonexistent_no_raise(tmp_path: Path) -> None:
    c = AudioChunker()
    missing = str(tmp_path / "does-not-exist")
    c._cleanup_dir(missing)  # should not raise


def test_probe_stream_info_timeout_returns_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = AudioChunker()
    audio = _make_tmp_audio(tmp_path)
    import subprocess as _sp

    def _boom(*args: object, **kwargs: object) -> object:
        raise _sp.TimeoutExpired(cmd="ffprobe", timeout=1)

    monkeypatch.setattr(_sp, "run", _boom)
    container, codec = c._probe_stream_info(audio)
    assert container == "" and codec == ""


def test_detect_silence_ignores_bad_timestamp(monkeypatch: pytest.MonkeyPatch) -> None:
    c = AudioChunker()

    # Fake ffmpeg output with one bad and one good silence_end line
    class _R:
        stdout = ""  # some tools write to stderr
        stderr = "silence_end: not_a_number\nmore\nsilence_end: 1.0\n"
        returncode = 0

    import subprocess as _sp

    def _fake_run(cmd: list[str], capture_output: bool, text: bool, timeout: int) -> object:
        return _R()

    monkeypatch.setattr(_sp, "run", _fake_run)
    out = c._detect_silence("/tmp/a.m4a", duration=10.0)
    assert out == [1.0]


def test_split_audio_prefers_webm_for_opus_and_handles_no_splits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = AudioChunker()
    audio = _make_tmp_audio(tmp_path)
    # Force codec=opus to exercise webm selection and pass-through branch when no split points
    monkeypatch.setattr(c, "_probe_stream_info", lambda _p: ("matroska,webm", "opus"))

    import subprocess as _sp

    def _fake_run_copy(cmd: list[str], **kwargs: object) -> object:
        # Should not be called when there are no split points; but keep safe
        out_path = cmd[-1]
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_bytes(b"x")

        class _R:
            stdout = ""
            stderr = ""
            returncode = 0

        return _R()

    monkeypatch.setattr(_sp, "run", _fake_run_copy)
    # Call with no split points to hit the single-chunk return
    res = c._split_audio(audio, split_points=[], total_duration=5.0)
    assert len(res) == 1 and res[0].path == audio


def test_calculate_split_points_logs_no_nearby_silence(monkeypatch: pytest.MonkeyPatch) -> None:
    c = AudioChunker(target_chunk_mb=1.0)
    # Provide silence points far away from ideal so the else-path is taken
    out = c._calculate_split_points(
        silence_points=[1000.0], total_duration=100.0, estimated_mb=50.0
    )
    assert out  # non-empty ideal points returned when no nearby silence found


def test_probe_stream_info_non_dict_streams_skip(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    c = AudioChunker()
    audio = _make_tmp_audio(tmp_path)

    class _PR:
        def __init__(self, s: str) -> None:
            self.stdout = s
            self.stderr = ""

    import json as _json
    import subprocess as _sp

    body = _json.dumps(
        {
            "format": {"format_name": "mp4"},
            "streams": [123, {"codec_type": "audio", "codec_name": "aac"}],
        }
    )

    monkeypatch.setattr(_sp, "run", lambda *a, **k: _PR(body))
    container, codec = c._probe_stream_info(audio)
    assert container == "mp4" and codec == "aac"


def test_probe_stream_info_streams_not_list(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    c = AudioChunker()
    audio = _make_tmp_audio(tmp_path)

    class _PR:
        def __init__(self, s: str) -> None:
            self.stdout = s
            self.stderr = ""

    import json as _json
    import subprocess as _sp

    body = _json.dumps({"format": {"format_name": "mp4"}, "streams": {"k": "v"}})
    monkeypatch.setattr(_sp, "run", lambda *a, **k: _PR(body))
    container, codec = c._probe_stream_info(audio)
    assert container == "mp4" and codec == ""


def test_probe_stream_info_streams_empty(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    c = AudioChunker()
    audio = _make_tmp_audio(tmp_path)

    class _PR:
        def __init__(self, s: str) -> None:
            self.stdout = s
            self.stderr = ""

    import json as _json
    import subprocess as _sp

    body = _json.dumps({"format": {"format_name": "mp4"}, "streams": []})
    monkeypatch.setattr(_sp, "run", lambda *a, **k: _PR(body))
    container, codec = c._probe_stream_info(audio)
    assert container == "mp4" and codec == ""
