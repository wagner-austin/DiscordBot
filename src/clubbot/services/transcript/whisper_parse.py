from __future__ import annotations

from .types import TranscriptSegment


def to_verbose_dict(obj: object) -> dict[str, object]:
    """Coerce OpenAI SDK response to a dict with 'text' and 'segments'."""
    data: dict[str, object] | None = None
    for meth in ("to_dict_recursive", "to_dict", "model_dump"):
        f = getattr(obj, meth, None)
        if callable(f):
            try:
                result = f()
                if isinstance(result, dict):
                    data = result
                    break
            except (TypeError, ValueError):
                continue
    if data is None and isinstance(obj, dict):
        data = obj
    if data is None:
        return {"text": "", "segments": []}
    return data


def convert_verbose_to_segments(obj: object) -> list[TranscriptSegment]:
    data = to_verbose_dict(obj)
    segs_raw = data.get("segments")
    out: list[TranscriptSegment] = []
    if isinstance(segs_raw, list):
        for item in segs_raw:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text", "")).strip()
            if not text:
                continue
            start = _as_float(item.get("start", 0.0))
            end = _as_float(item.get("end", start))
            duration = max(0.0, end - start)
            out.append(TranscriptSegment(text=text, start=start, duration=duration))
    return out


def _as_float(val: object) -> float:
    if isinstance(val, int | float):
        return float(val)
    if isinstance(val, str):
        try:
            return float(val)
        except ValueError:
            return 0.0
    return 0.0
