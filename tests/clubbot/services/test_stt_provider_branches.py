from __future__ import annotations

from pathlib import Path

import pytest
import src.clubbot.services.transcript.stt_provider as stt_mod


def _provider(enable_chunking: bool = False) -> stt_mod.STTTranscriptProvider:
    # Use minimal valid config; __post_init__ sets up OpenAI client but won't call network
    return stt_mod.STTTranscriptProvider(
        api_key="sk-test",
        max_video_seconds=3600,
        max_file_mb=25,
        enable_chunking=enable_chunking,
    )


def test_should_chunk_returns_false_when_disabled(tmp_path: Path) -> None:
    p = tmp_path / "a.m4a"
    p.write_bytes(b"x")
    prov = _provider(enable_chunking=False)
    assert prov._should_chunk(str(p)) is False


def test_transcribe_chunked_raises_when_ffmpeg_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    p = tmp_path / "a.m4a"
    p.write_bytes(b"x")
    prov = _provider(enable_chunking=True)
    monkeypatch.setattr(prov, "_ffmpeg_available", lambda: False)
    with pytest.raises(stt_mod.UserInputError):
        _ = prov._transcribe_chunked(str(p))


def test_estimate_skips_nondict_and_no_audio_formats(monkeypatch: pytest.MonkeyPatch) -> None:
    # Craft probe response with one nondict element and one with acodec none
    info = {
        "duration": "120",
        "formats": [
            "bad",
            {"vcodec": "h264", "acodec": "aac"},  # skipped (video)
            {"vcodec": "none", "acodec": "none", "abr": "96"},  # skipped (no audio)
        ],
    }

    prov = _provider(enable_chunking=False)
    monkeypatch.setattr(prov, "_probe", lambda url: info)
    dur, approx_mb = prov.estimate("https://x")
    assert dur == 120 and approx_mb >= 0.0


def test_estimate_fallback_abr_without_size(monkeypatch: pytest.MonkeyPatch) -> None:
    info = {
        "duration": "60",
        "formats": [
            {"vcodec": "none", "acodec": "opus", "abr": "96"},  # audio-only w/o explicit size
        ],
    }
    prov = _provider(enable_chunking=False)
    monkeypatch.setattr(prov, "_probe", lambda url: info)
    dur, approx_mb = prov.estimate("https://x")
    assert dur == 60 and approx_mb > 0.0


def test_estimate_fallback_with_higher_abr(monkeypatch: pytest.MonkeyPatch) -> None:
    info = {
        "duration": 120,
        "formats": [
            {"vcodec": "none", "acodec": "mp4a.40.2", "abr": 192},
        ],
    }
    prov = _provider(enable_chunking=False)
    monkeypatch.setattr(prov, "_probe", lambda url: info)
    dur, approx_mb = prov.estimate("https://x")
    assert dur == 120 and approx_mb > 0.0


def test_estimate_formats_not_list(monkeypatch: pytest.MonkeyPatch) -> None:
    info = {"duration": 60, "formats": {"k": "v"}}
    prov = _provider(enable_chunking=False)
    monkeypatch.setattr(prov, "_probe", lambda url: info)
    dur, approx_mb = prov.estimate("https://x")
    assert dur == 60 and approx_mb == 0.0
