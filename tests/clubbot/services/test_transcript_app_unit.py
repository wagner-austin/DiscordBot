from __future__ import annotations

from types import SimpleNamespace

import pytest
import src.clubbot.services.transcript.app as app_mod


def _cfg(**kw: object):
    base = {
        "TRANSCRIPT_PROVIDER": "youtube",
        "OPENAI_API_KEY": None,
        "TRANSCRIPT_MAX_VIDEO_SECONDS": 5400,
        "TRANSCRIPT_MAX_FILE_MB": 25,
        "TRANSCRIPT_STT_API_TIMEOUT_SECONDS": 900,
        "TRANSCRIPT_STT_API_MAX_RETRIES": 2,
        "TRANSCRIPT_COOKIES_TEXT": None,
        "TRANSCRIPT_COOKIES_PATH": None,
        "TRANSCRIPT_ENABLE_CHUNKING": True,
        "TRANSCRIPT_CHUNK_THRESHOLD_MB": 20.0,
        "TRANSCRIPT_TARGET_CHUNK_MB": 20.0,
        "TRANSCRIPT_MAX_CHUNK_DURATION_SECONDS": 600.0,
        "TRANSCRIPT_MAX_CONCURRENT_CHUNKS": 3,
        "TRANSCRIPT_SILENCE_THRESHOLD_DB": -40.0,
        "TRANSCRIPT_SILENCE_DURATION_SECONDS": 0.5,
        "TRANSCRIPT_STT_RTF": 0.5,
        "TRANSCRIPT_DL_MIB_PER_SEC": 4.0,
        "TRANSCRIPT_PREFERRED_LANGS": "",
    }
    base.update(kw)
    return SimpleNamespace(**base)


def test_parse_langs_defaults_and_custom() -> None:
    # Default languages when spec empty
    assert app_mod._parse_langs("") == app_mod.DEFAULT_TRANSCRIPT_LANGS
    assert app_mod._parse_langs(None) == app_mod.DEFAULT_TRANSCRIPT_LANGS
    # Custom list parsing
    assert app_mod._parse_langs("en, es , ja ") == ["en", "es", "ja"]


def test_transcript_service_youtube_provider_initialization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = _cfg(TRANSCRIPT_PROVIDER="youtube")
    svc = app_mod.TranscriptService(cfg)

    # Swap provider to a fake that returns controlled segments for fetch_cleaned
    class _Prov:
        def fetch(self, vid: str, opts):
            return [SimpleNamespace(text="hi", start=0.0, duration=1.0)]

    svc._set_provider_for_tests(_Prov())
    out = svc.fetch_cleaned("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert out.video_id == "dQw4w9WgXcQ" and "hi" in out.text


def test_transcript_service_stt_requires_key() -> None:
    cfg = _cfg(TRANSCRIPT_PROVIDER="stt", OPENAI_API_KEY=None)
    with pytest.raises(RuntimeError):
        _ = app_mod.TranscriptService(cfg)


def test_transcript_service_stt_initializes_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = _cfg(TRANSCRIPT_PROVIDER="stt", OPENAI_API_KEY="sk-123")
    created: dict[str, object] = {}

    class _FakeSTT:
        def __init__(self, **kwargs):
            created.update(kwargs)

    monkeypatch.setattr(app_mod, "STTTranscriptProvider", _FakeSTT)
    _ = app_mod.TranscriptService(cfg)
    # Ensure all key config knobs were passed through
    assert created.get("api_key") == "sk-123"
    assert float(created.get("max_chunk_duration", 0.0)) > 0.0
