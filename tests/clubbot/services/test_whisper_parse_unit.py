from __future__ import annotations

import src.clubbot.services.transcript.whisper_parse as wmod


class _Obj1:
    def to_dict(self) -> dict[str, object]:
        return {"text": "", "segments": []}


class _Obj2:
    def to_dict_recursive(self) -> dict[str, object]:
        return {"text": "all", "segments": [{"text": " a ", "start": "0.0", "end": "1.0"}]}


def test_to_verbose_dict_prefers_methods_and_handles_exceptions() -> None:
    # Use object with to_dict_recursive
    d = wmod.to_verbose_dict(_Obj2())
    assert isinstance(d, dict) and "segments" in d
    # Fallback when dict passed directly
    d2 = wmod.to_verbose_dict({"text": "x", "segments": []})
    assert d2["text"] == "x"
    # When no method and not dict -> default shape
    d3 = wmod.to_verbose_dict(object())
    assert d3 == {"text": "", "segments": []}


def test_to_verbose_dict_method_raises_and_is_ignored() -> None:
    class _Bad:
        def to_dict(self) -> dict[str, object]:
            raise TypeError("boom")

    d = wmod.to_verbose_dict(_Bad())
    assert d == {"text": "", "segments": []}


def test_convert_verbose_to_segments_strips_and_parses_numbers() -> None:
    payload = {
        "segments": [
            {"text": "  hello  ", "start": "1.5", "end": "3.0"},
            {"text": "   ", "start": 0, "end": 0},
            123,
        ]
    }
    out = wmod.convert_verbose_to_segments(payload)
    assert len(out) == 1 and out[0].text == "hello" and out[0].duration == 1.5


def test_as_float_edges() -> None:
    f = wmod._as_float
    assert f(5) == 5.0
    assert f("7.25") == 7.25
    assert f("bad") == 0.0
    assert f(object()) == 0.0
