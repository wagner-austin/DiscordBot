from __future__ import annotations

from types import SimpleNamespace

import pytest
import src.clubbot.services.transcript.provider as provider_mod
from src.clubbot.services.transcript.provider import YouTubeTranscriptProvider
from src.clubbot.services.transcript.types import TranscriptOptions
from src.clubbot.utils.errors import UserInputError


def test_as_float_edges_provider() -> None:
    f = provider_mod._as_float
    assert f(5) == 5.0
    assert f(3.25) == 3.25
    assert f("7.5") == 7.5
    assert f("bad") == 0.0
    assert f(object()) == 0.0


def test_coerce_raw_items_typing_and_non_list() -> None:
    with pytest.raises(UserInputError):
        _ = provider_mod._coerce_raw_items({})

    obj = [
        {"text": " hello ", "start": "1.0", "duration": "2.0"},
        {"text": "", "start": 0, "duration": 0},
        123,  # not a dict
    ]
    out = provider_mod._coerce_raw_items(obj)
    assert out
    assert out[0]["text"].strip() == "hello"
    assert out[0]["start"] == 1.0 and out[0]["duration"] == 2.0


def test_fetch_transforms_items_with_as_float(monkeypatch: pytest.MonkeyPatch) -> None:
    prov = YouTubeTranscriptProvider()

    def fake_get_transcript(video_id: str, languages: list[str]) -> list[dict[str, object]]:
        return [
            {"text": "\tkeep me\n", "start": "0", "duration": "1.5"},
            {"text": "   ", "start": 0, "duration": 0},  # skipped due to blank
        ]

    monkeypatch.setattr(
        provider_mod, "YouTubeTranscriptApi", SimpleNamespace(get_transcript=fake_get_transcript)
    )
    out = prov.fetch("vid", TranscriptOptions(preferred_langs=["en"]))
    assert len(out) == 1
    assert out[0].text.strip() == "keep me" and out[0].start == 0.0 and out[0].duration == 1.5


def test_fetch_raw_video_unavailable_and_parse_error(monkeypatch: pytest.MonkeyPatch) -> None:
    prov = YouTubeTranscriptProvider()

    class _VideoUnavailableError(Exception):
        pass

    class _ParseError(Exception):
        pass

    # Map provider exception names to our fake ones
    monkeypatch.setattr(provider_mod, "VideoUnavailable", _VideoUnavailableError, raising=True)
    monkeypatch.setattr(provider_mod, "ET", SimpleNamespace(ParseError=_ParseError))

    # VideoUnavailable path
    def _raise_vu(*_: object, **__: object) -> None:
        raise _VideoUnavailableError()

    monkeypatch.setattr(
        provider_mod,
        "YouTubeTranscriptApi",
        SimpleNamespace(get_transcript=_raise_vu),
    )
    with pytest.raises(UserInputError):
        prov._fetch_raw("vid", ["en"])

    # ParseError path
    def _raise_pe(*_: object, **__: object) -> None:
        raise _ParseError()

    monkeypatch.setattr(
        provider_mod,
        "YouTubeTranscriptApi",
        SimpleNamespace(get_transcript=_raise_pe),
    )
    with pytest.raises(UserInputError):
        prov._fetch_raw("vid", ["en"])


def test_fetch_raw_generic_exception_logs_and_bubbles(monkeypatch: pytest.MonkeyPatch) -> None:
    prov = YouTubeTranscriptProvider()

    def _raise_generic(*_: object, **__: object) -> None:
        raise RuntimeError("x")

    monkeypatch.setattr(
        provider_mod,
        "YouTubeTranscriptApi",
        SimpleNamespace(get_transcript=_raise_generic),
    )
    with pytest.raises(RuntimeError):
        prov._fetch_raw("vid", ["en"])


def test_list_transcripts_disabled_and_unexpected_type(monkeypatch: pytest.MonkeyPatch) -> None:
    prov = YouTubeTranscriptProvider()

    class _TranscriptsDisabledError(Exception):
        pass

    monkeypatch.setattr(
        provider_mod, "TranscriptsDisabled", _TranscriptsDisabledError, raising=True
    )
    # Raise disabled when listing
    monkeypatch.setattr(
        provider_mod,
        "YouTubeTranscriptApi",
        SimpleNamespace(
            list_transcripts=lambda *_: (_ for _ in ()).throw(_TranscriptsDisabledError())
        ),
    )
    with pytest.raises(UserInputError):
        _ = prov._list_transcripts("vid")

    # Return unexpected type
    monkeypatch.setattr(
        provider_mod,
        "YouTubeTranscriptApi",
        SimpleNamespace(list_transcripts=lambda *_: {"bad": True}),
    )
    with pytest.raises(UserInputError):
        _ = prov._list_transcripts("vid")


def test_choose_transcript_translate_fallback_and_none(monkeypatch: pytest.MonkeyPatch) -> None:
    prov = YouTubeTranscriptProvider()

    class _Res:
        def fetch(self) -> list[dict[str, object]]:
            return [{"text": "x", "start": 0, "duration": 1}]

    class _List:
        def __init__(self, found: bool, can_translate: bool) -> None:
            self._found = found
            self._can = can_translate

        def find_transcript(self, languages: list[str]):
            if self._found:
                return _Res()
            raise provider_mod.NoTranscriptFound("vid", languages, {})

        def translate(self, lang: str):
            if self._can:
                return _Res()
            raise RuntimeError("no translate")

    # Found directly
    t = prov._choose_transcript(_List(True, True), ["en"])
    assert t is not None
    # Fallback translate
    t2 = prov._choose_transcript(_List(False, True), ["en"])
    assert t2 is not None
    # None when not found and translate fails
    t3 = prov._choose_transcript(_List(False, False), ["en"])
    assert t3 is None
