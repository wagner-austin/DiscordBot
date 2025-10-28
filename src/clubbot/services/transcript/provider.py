from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from typing import Protocol, runtime_checkable

from youtube_transcript_api import (
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
    YouTubeTranscriptApi,
)

from ...utils.errors import UserInputError
from .types import (
    DEFAULT_TRANSCRIPT_LANGS,
    RawTranscriptItem,
    TranscriptOptions,
    TranscriptSegment,
)


@runtime_checkable
class _TranscriptResource(Protocol):
    def fetch(self) -> list[RawTranscriptItem]: ...


@runtime_checkable
class _TranscriptListing(Protocol):
    def find_transcript(self, languages: list[str]) -> _TranscriptResource: ...
    def translate(self, language: str) -> _TranscriptResource: ...


class TranscriptProvider(Protocol):
    def fetch(self, video_id: str, opts: TranscriptOptions) -> list[TranscriptSegment]: ...


class YouTubeTranscriptProvider:
    def __init__(self) -> None:
        self._logger = logging.getLogger(__name__)

    def fetch(self, video_id: str, opts: TranscriptOptions) -> list[TranscriptSegment]:
        langs = opts.preferred_langs or DEFAULT_TRANSCRIPT_LANGS
        raw = self._fetch_raw(video_id, langs)
        out: list[TranscriptSegment] = []
        for item in raw:
            text = str(item.get("text", ""))
            # Normalize typical '[Music]' filler to empty, keep if actual words
            if not text.strip():
                continue
            start = _as_float(item.get("start", 0.0))
            duration = _as_float(item.get("duration", 0.0))
            out.append(TranscriptSegment(text=text, start=start, duration=duration))
        return out

    def _fetch_raw(self, video_id: str, langs: list[str]) -> list[RawTranscriptItem]:
        try:
            raw_obj: object = YouTubeTranscriptApi.get_transcript(video_id, languages=langs)
        except NoTranscriptFound:
            return self._fallback_listing(video_id, langs)
        except TranscriptsDisabled:
            raise UserInputError("Transcripts are disabled for this video") from None
        except VideoUnavailable:
            raise UserInputError("The video is unavailable or private") from None
        except ET.ParseError:
            raise UserInputError(
                "Captions could not be fetched (possibly blocked or unavailable)."
            ) from None
        except Exception as exc:
            self._logger.exception("Transcript fetch error: %s", exc)
            raise

        return _coerce_raw_items(raw_obj)

    def _fallback_listing(self, video_id: str, langs: list[str]) -> list[RawTranscriptItem]:
        listing = self._list_transcripts(video_id)
        chosen = self._choose_transcript(listing, langs)
        if chosen is None:
            raise UserInputError("No transcript is available for this video") from None
        return _coerce_raw_items(chosen.fetch())

    def _list_transcripts(self, video_id: str) -> _TranscriptListing:
        try:
            listing_obj: object = YouTubeTranscriptApi.list_transcripts(video_id)
        except VideoUnavailable:
            raise UserInputError("The video is unavailable or private") from None
        except TranscriptsDisabled:
            raise UserInputError("Transcripts are disabled for this video") from None
        except Exception as exc:  # pragma: no cover - depends on network
            self._logger.exception("Failed to list transcripts: %s", exc)
            raise

        if isinstance(listing_obj, _TranscriptListing):
            return listing_obj
        # If the library type changes, fail clearly
        raise UserInputError("Unexpected transcript listing type")

    def _choose_transcript(
        self, listing: _TranscriptListing, langs: list[str]
    ) -> _TranscriptResource | None:
        # Try exact language matches first
        for code in langs:
            try:
                t = listing.find_transcript([code])
            except NoTranscriptFound:
                t = None
            if t is not None:
                return t
        # Fallback: try translation to first preferred
        try:
            return listing.translate(langs[0])
        except Exception as exc:  # pragma: no cover - depends on network
            self._logger.debug("Could not translate transcript: %s", exc)
            return None


def _as_float(val: object) -> float:
    if isinstance(val, int | float):
        return float(val)
    if isinstance(val, str):
        try:
            return float(val)
        except ValueError:
            return 0.0
    return 0.0


def _coerce_raw_items(obj: object) -> list[RawTranscriptItem]:
    if not isinstance(obj, list):
        raise UserInputError("Unexpected transcript payload format")
    out: list[RawTranscriptItem] = []
    for item in obj:
        if not isinstance(item, dict):
            continue
        text_v = str(item.get("text", ""))
        start_v = _as_float(item.get("start", 0.0))
        dur_v = _as_float(item.get("duration", 0.0))
        typed: RawTranscriptItem = {"text": text_v, "start": start_v, "duration": dur_v}
        out.append(typed)
    return out
