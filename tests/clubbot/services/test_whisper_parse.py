from __future__ import annotations

from types import SimpleNamespace

from src.clubbot.services.transcript.whisper_parse import (
    convert_verbose_to_segments,
    to_verbose_dict,
)


def test_to_verbose_dict_accepts_dict_and_model_dump() -> None:
    d = {"text": "hello", "segments": []}
    assert to_verbose_dict(d) == d

    obj = SimpleNamespace(model_dump=lambda: d)
    assert to_verbose_dict(obj) == d


def test_convert_verbose_to_segments_filters_and_parses() -> None:
    payload = {
        "segments": [
            {"text": " one ", "start": "0.0", "end": 1.5},
            {"text": "", "start": 1, "end": 2},  # filtered
            {"text": "two", "start": 2, "end": 4},
        ]
    }
    segs = convert_verbose_to_segments(payload)
    assert len(segs) == 2
    assert segs[0].text == "one" and segs[0].start == 0.0 and segs[0].duration == 1.5
    assert segs[1].text == "two" and segs[1].duration == 2.0
