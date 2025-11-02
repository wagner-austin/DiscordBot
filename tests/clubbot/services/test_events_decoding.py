from __future__ import annotations

import json

from src.clubbot.services.jobs.events import try_decode_event


def test_decode_completed_event_ok() -> None:
    payload = json.dumps(
        {
            "type": "completed",
            "request_id": "r1",
            "user_id": 42,
            "url": "https://x",
            "video_id": "vid",
            "content_key": "k1",
        }
    )
    evt = try_decode_event(payload)
    assert evt is not None and evt["type"] == "completed" and evt["content_key"] == "k1"


def test_decode_completed_event_missing_field_returns_none() -> None:
    payload = json.dumps(
        {
            "type": "completed",
            "request_id": "r1",
            "user_id": 42,
            "url": "https://x",
            "video_id": "vid",
        }
    )
    assert try_decode_event(payload) is None


def test_decode_failed_user_and_system() -> None:
    for kind in ("user", "system"):
        payload = json.dumps(
            {
                "type": "failed",
                "request_id": "r1",
                "user_id": 42,
                "error_kind": kind,
                "message": "m",
            }
        )
        evt = try_decode_event(payload)
        assert evt is not None
        assert evt["type"] == "failed" and evt["error_kind"] in {"user", "system"}


def test_decode_failed_invalid_kind_returns_none() -> None:
    payload = json.dumps(
        {
            "type": "failed",
            "request_id": "r1",
            "user_id": 42,
            "error_kind": "other",
            "message": "m",
        }
    )
    assert try_decode_event(payload) is None


def test_decode_unknown_type_or_invalid_json() -> None:
    assert try_decode_event(json.dumps({"type": "other"})) is None
    assert try_decode_event("not json") is None
    assert try_decode_event(json.dumps([1, 2, 3])) is None
