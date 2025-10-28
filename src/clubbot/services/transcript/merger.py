from __future__ import annotations

from collections.abc import Iterable

from .types import AudioChunk, TranscriptSegment


class TranscriptMerger:
    def merge(
        self,
        chunk_results: list[tuple[AudioChunk, list[TranscriptSegment]]],
    ) -> list[TranscriptSegment]:
        """Merge segments from all chunks into a single ordered transcript.

        Adjust start timestamps by each chunk's start offset, concatenate, then sort.
        """
        import logging

        logger = logging.getLogger(__name__)
        adjusted: list[TranscriptSegment] = []
        for idx, (chunk, segs) in enumerate(chunk_results):
            if not segs:
                logger.warning("Chunk %d has no segments (start=%.1fs)", idx, chunk.start_seconds)
                continue
            logger.debug(
                "Merging chunk %d: %d segments (start=%.1fs, duration=%.1fs)",
                idx,
                len(segs),
                chunk.start_seconds,
                chunk.duration_seconds,
            )
            adjusted.extend(self._adjust_timestamps(segs, chunk.start_seconds))
        # Defensive: ensure ordered by start time
        adjusted.sort(key=lambda s: s.start)
        logger.info(
            "Merge complete: %d total segments from %d chunks", len(adjusted), len(chunk_results)
        )
        return adjusted

    def _adjust_timestamps(
        self, segments: Iterable[TranscriptSegment], offset_seconds: float
    ) -> list[TranscriptSegment]:
        out: list[TranscriptSegment] = []
        for seg in segments:
            out.append(
                TranscriptSegment(
                    text=seg.text,
                    start=max(0.0, seg.start + offset_seconds),
                    duration=seg.duration,
                )
            )
        return out
