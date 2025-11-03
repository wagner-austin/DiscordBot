from __future__ import annotations

from types import SimpleNamespace

from src.clubbot.services.transcript.merger import TranscriptMerger


def test_merger_warns_on_empty_chunk_and_merges_ordered() -> None:
    m = TranscriptMerger()
    # Build one empty and one non-empty chunk result
    chunk_empty = SimpleNamespace(start_seconds=0.0, duration_seconds=1.0)
    chunk_filled = SimpleNamespace(start_seconds=2.0, duration_seconds=1.0)
    segs = [SimpleNamespace(text="a", start=0.0, duration=1.0)]
    out = m.merge([(chunk_empty, []), (chunk_filled, segs)])
    assert len(out) == 1 and out[0].start >= 2.0
