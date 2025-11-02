from __future__ import annotations

import json
from typing import Final, Literal, TypedDict

# Channel and key naming
DEFAULT_EVENTS_CHANNEL: Final[str] = "transcript:events"
DEFAULT_RESULT_KEY_PREFIX: Final[str] = "transcript:result:"


class TranscriptCompletedEvent(TypedDict):
    type: Literal["completed"]
    request_id: str
    user_id: int
    url: str
    video_id: str
    content_key: str


class TranscriptFailedEvent(TypedDict):
    type: Literal["failed"]
    request_id: str
    user_id: int
    error_kind: Literal["user", "system"]
    message: str


def build_result_key(prefix: str, request_id: str) -> str:
    return f"{prefix}{request_id}"


def encode_event(event: TranscriptCompletedEvent | TranscriptFailedEvent) -> str:
    return json.dumps(event, separators=(",", ":"))


def try_decode_event(payload: str) -> TranscriptCompletedEvent | TranscriptFailedEvent | None:
    try:
        obj = json.loads(payload)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    typ = obj.get("type")
    if typ == "completed":
        # Validate fields and types strictly
        rq = obj.get("request_id")
        uid = obj.get("user_id")
        url = obj.get("url")
        vid = obj.get("video_id")
        ckey = obj.get("content_key")
        if (
            isinstance(rq, str)
            and isinstance(uid, int)
            and isinstance(url, str)
            and isinstance(vid, str)
            and isinstance(ckey, str)
        ):
            return {
                "type": "completed",
                "request_id": rq,
                "user_id": uid,
                "url": url,
                "video_id": vid,
                "content_key": ckey,
            }
        return None
    if typ == "failed":
        rq = obj.get("request_id")
        uid = obj.get("user_id")
        kind = obj.get("error_kind")
        msg = obj.get("message")
        if (
            isinstance(rq, str)
            and isinstance(uid, int)
            and kind in ("user", "system")
            and isinstance(msg, str)
        ):
            error_kind: Literal["user", "system"] = "user" if kind == "user" else "system"
            return {
                "type": "failed",
                "request_id": rq,
                "user_id": uid,
                "error_kind": error_kind,
                "message": msg,
            }
        return None
    return None
