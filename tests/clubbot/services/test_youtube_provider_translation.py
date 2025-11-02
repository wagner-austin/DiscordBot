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


class _ListingNoDirect:
    def __init__(self, can_translate: bool = True) -> None:
        self._can_translate = can_translate

    def find_transcript(self, languages: list[str]) -> None:
        # Simulate no direct transcript for preferred languages
        from src.clubbot.services.transcript.provider import NoTranscriptFound

        raise NoTranscriptFound()

    def translate(self, language: str):
        if not self._can_translate:
            raise RuntimeError("translate failed")
        return _FakeResource([{"text": "translated", "start": 0, "duration": 1}])


def test_translation_fallback_uses_translate(monkeypatch: pytest.MonkeyPatch) -> None:
    prov = YouTubeTranscriptProvider()

    # NoTranscriptFound on direct fetch
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
            list_transcripts=lambda vid: _ListingNoDirect(can_translate=True),
        ),
        raising=True,
    )

    out = prov.fetch("vid", SimpleNamespace(preferred_langs=["en"]))
    assert out and out[0].text == "translated"


def test_translation_fallback_raises_when_translate_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
            list_transcripts=lambda vid: _ListingNoDirect(can_translate=False),
        ),
        raising=True,
    )

    with pytest.raises(UserInputError):
        prov.fetch("vid", SimpleNamespace(preferred_langs=["en"]))


def test_list_transcripts_error_mapped_to_user(monkeypatch: pytest.MonkeyPatch) -> None:
    prov = YouTubeTranscriptProvider()

    class NoTranscriptFoundError(Exception):
        pass

    class VideoUnavailableError(Exception):
        pass

    monkeypatch.setattr(provider_mod, "NoTranscriptFound", NoTranscriptFoundError, raising=True)
    monkeypatch.setattr(provider_mod, "VideoUnavailable", VideoUnavailableError, raising=True)

    def raising_get_transcript(*args: object, **kwargs: object) -> list[dict[str, object]]:
        raise NoTranscriptFoundError()

    def raising_list_transcripts(video_id: str):
        raise VideoUnavailableError()

    monkeypatch.setattr(
        provider_mod,
        "YouTubeTranscriptApi",
        SimpleNamespace(
            get_transcript=raising_get_transcript,
            list_transcripts=raising_list_transcripts,
        ),
        raising=True,
    )

    with pytest.raises(UserInputError):
        prov.fetch("vid", SimpleNamespace(preferred_langs=["en"]))
