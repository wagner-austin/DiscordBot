from __future__ import annotations

import os
import tempfile
from contextlib import suppress
from typing import BinaryIO, Literal

from src.clubbot.services.transcript.parallel import ParallelTranscriber
from src.clubbot.services.transcript.types import AudioChunk


def _make_chunk(contents: bytes, start: float, dur: float) -> AudioChunk:
    fd, path = tempfile.mkstemp(prefix="chunk_", suffix=".bin")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(contents)
    except Exception:
        os.close(fd)
        raise
    return AudioChunk(
        path=path,
        start_seconds=start,
        duration_seconds=dur,
        size_bytes=len(contents),
    )


def test_parallel_transcriber_returns_segments_per_chunk(tmp_path: str = "") -> None:
    # Fake transcribe that returns one segment per input file
    def fake_transcribe(
        *,
        model: str,
        file: BinaryIO,
        response_format: Literal["verbose_json"],
        timeout: float | None = None,
    ) -> object:
        data = file.read()
        return {"segments": [{"text": f"{len(data)} bytes", "start": 0, "end": 1}]}

    pt = ParallelTranscriber(transcribe=fake_transcribe, max_concurrent=2, max_retries=0)
    chunks = [
        _make_chunk(b"aaa", 0.0, 1.0),
        _make_chunk(b"bbbb", 1.0, 1.0),
        _make_chunk(b"cc", 2.0, 1.0),
    ]
    try:
        out = pt.transcribe_chunks(chunks)
        assert len(out) == len(chunks)
        assert [len(s) for s in out] == [1, 1, 1]
        assert out[0][0].text.endswith("3 bytes")
    finally:
        for c in chunks:
            with suppress(OSError):
                os.remove(c.path)
