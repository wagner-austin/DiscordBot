from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, TypedDict, runtime_checkable

# Default language preference list for transcript fetching
DEFAULT_TRANSCRIPT_LANGS = ["en", "en-US", "en-GB"]


@dataclass(frozen=True)
class TranscriptSegment:
    text: str
    start: float
    duration: float


@dataclass(frozen=True)
class AudioChunk:
    """Represents a physical audio file chunk and its time window in the source."""

    path: str
    start_seconds: float
    duration_seconds: float
    size_bytes: int


# Alias for readability in signatures
TranscriptSegmentList = list[TranscriptSegment]


@dataclass(frozen=True)
class TranscriptOptions:
    preferred_langs: list[str]


@dataclass(frozen=True)
class TranscriptResult:
    url: str
    video_id: str
    text: str


class RawTranscriptItem(TypedDict):
    text: str
    start: float
    duration: float


@runtime_checkable
class SupportsEstimate(Protocol):
    def estimate(self, url: str) -> tuple[int, float]: ...
