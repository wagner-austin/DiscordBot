from __future__ import annotations

import re

from .types import TranscriptSegment

_STAMP_RE = re.compile(r"\b\d{1,2}:\d{2}:\d{2}(?:\.\d{1,3})?\b")
_WS_RE = re.compile(r"\s+")


def strip_timestamps(text: str) -> str:
    """Remove common timestamp tokens like 00:00:04.520 from free text."""
    cleaned = _STAMP_RE.sub(" ", text)
    # Drop obvious placeholders
    cleaned = cleaned.replace("No text", " ")
    return _WS_RE.sub(" ", cleaned).strip()


def clean_segments(segments: list[TranscriptSegment]) -> str:
    # Join with spaces; segments are small utterances.
    raw = " ".join(s.text for s in segments if s.text.strip())
    return strip_timestamps(raw)
