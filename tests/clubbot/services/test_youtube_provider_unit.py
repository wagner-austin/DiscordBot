from __future__ import annotations

from types import SimpleNamespace

import pytest
import src.clubbot.services.transcript.provider as provider_mod
from src.clubbot.services.transcript.provider import YouTubeTranscriptProvider
from src.clubbot.utils.errors import UserInputError


class _FakeResource:
    def __init__(self, data: list[dict[str, object]]) -> None:
        self._data = data

    def fetch(self) -> list[dict[str, object]]:
        return self._data


class _FakeListing:
    def __init__(self, found: bool = True) -> None:
        self._found = found

    def find_transcript(self, languages: list[str]) -> _FakeResource:
        if not self._found:
            # Use the provider module's reference so monkeypatching works
            raise provider_mod.NoTranscriptFound("vid", languages, {})
        return _FakeResource([{"text": "ok", "start": 0, "duration": 1}])

    def translate(self, language: str) -> _FakeResource:
        return _FakeResource([{"text": "t", "start": 0, "duration": 1}])


def test_fetch_uses_get_transcript_when_available(monkeypatch: pytest.MonkeyPatch) -> None:
    prov = YouTubeTranscriptProvider()

    def fake_get_transcript(video_id: str, languages: list[str]) -> list[dict[str, object]]:
        return [{"text": "hello", "start": "0", "duration": 1}]

    monkeypatch.setattr(
        provider_mod,
        "YouTubeTranscriptApi",
        SimpleNamespace(
            get_transcript=fake_get_transcript,
            list_transcripts=lambda vid: _FakeListing(),
        ),
        raising=True,
    )

    out = prov.fetch("vid", SimpleNamespace(preferred_langs=["en"]))
    assert out and out[0].text == "hello" and out[0].start == 0.0


def test_fetch_falls_back_to_listing(monkeypatch: pytest.MonkeyPatch) -> None:
    prov = YouTubeTranscriptProvider()

    class NoTranscriptFoundError(Exception):
        pass

    monkeypatch.setattr(provider_mod, "NoTranscriptFound", NoTranscriptFoundError, raising=True)

    def raising_get_transcript(*args: object, **kwargs: object) -> list[dict[str, object]]:
        raise NoTranscriptFoundError()

    monkeypatch.setattr(
        provider_mod,
        "YouTubeTranscriptApi",
        SimpleNamespace(
            get_transcript=raising_get_transcript,
            list_transcripts=lambda vid: _FakeListing(found=False),
        ),
        raising=True,
    )
    out = prov.fetch("vid", SimpleNamespace(preferred_langs=["en"]))
    assert out and out[0].text in {"t"}


def test_fetch_maps_errors_to_user_input(monkeypatch: pytest.MonkeyPatch) -> None:
    prov = YouTubeTranscriptProvider()

    class TranscriptsDisabledError(Exception):
        pass

    class VideoUnavailableError(Exception):
        pass

    def bad_get(*_: object, **__: object) -> list[dict[str, object]]:
        raise TranscriptsDisabledError()

    monkeypatch.setattr(provider_mod, "TranscriptsDisabled", TranscriptsDisabledError, raising=True)
    monkeypatch.setattr(provider_mod, "VideoUnavailable", VideoUnavailableError, raising=True)
    monkeypatch.setattr(
        provider_mod,
        "YouTubeTranscriptApi",
        SimpleNamespace(
            get_transcript=bad_get,
            list_transcripts=lambda vid: _FakeListing(),
        ),
        raising=True,
    )
    with pytest.raises(UserInputError):
        prov.fetch("vid", SimpleNamespace(preferred_langs=["en"]))
