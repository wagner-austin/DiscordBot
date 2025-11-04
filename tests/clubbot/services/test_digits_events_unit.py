from __future__ import annotations

from src.clubbot.services.jobs.digits_events import (
    DEFAULT_DIGITS_EVENTS_CHANNEL,
    encode_event,
    try_decode_event,
)


def test_digits_events_encode_decode_roundtrip() -> None:
    started = {
        "type": "started",
        "request_id": "r1",
        "user_id": 1,
        "model_id": "m",
        "total_epochs": 10,
    }
    s = encode_event(started)  # should be JSON
    evt = try_decode_event(s)
    assert evt is not None and evt["type"] == "started"
    assert DEFAULT_DIGITS_EVENTS_CHANNEL == "digits:events"

    progress = {
        "type": "progress",
        "request_id": "r1",
        "user_id": 1,
        "model_id": "m",
        "epoch": 3,
        "total_epochs": 10,
        "val_acc": 0.95,
    }
    s2 = encode_event(progress)
    evt2 = try_decode_event(s2)
    assert evt2 is not None and evt2["type"] == "progress"

    completed = {
        "type": "completed",
        "request_id": "r1",
        "user_id": 1,
        "model_id": "m",
        "run_id": "rid",
        "val_acc": 0.97,
    }
    s3 = encode_event(completed)
    evt3 = try_decode_event(s3)
    assert evt3 is not None and evt3["type"] == "completed"

    failed = {
        "type": "failed",
        "request_id": "r1",
        "user_id": 1,
        "model_id": "m",
        "error_kind": "system",
        "message": "boom",
    }
    s4 = encode_event(failed)
    evt4 = try_decode_event(s4)
    assert evt4 is not None and evt4["type"] == "failed"


def test_digits_events_decode_invalid_json_and_non_dict() -> None:
    assert try_decode_event("not json") is None
    assert try_decode_event("[]") is None


def test_digits_events_decode_started_missing_fields() -> None:
    bad = {"type": "started", "request_id": "r", "user_id": 1, "model_id": "m"}
    assert try_decode_event(encode_event(bad)) is None


def test_digits_events_decode_progress_invalid_types() -> None:
    bad = {
        "type": "progress",
        "request_id": "r",
        "user_id": 1,
        "model_id": "m",
        "epoch": "3",  # wrong type
        "total_epochs": 10,
        "val_acc": None,
    }
    assert try_decode_event(encode_event(bad)) is None


def test_digits_events_decode_completed_invalid_types() -> None:
    bad = {
        "type": "completed",
        "request_id": "r",
        "user_id": 1,
        "model_id": "m",
        "run_id": "rid",
        "val_acc": "0.95",  # wrong type
    }
    assert try_decode_event(encode_event(bad)) is None


def test_digits_events_decode_unknown_type() -> None:
    unknown = {"type": "foo", "request_id": "r", "user_id": 1, "model_id": "m"}
    assert try_decode_event(encode_event(unknown)) is None


def test_digits_events_decode_failed_invalid_types() -> None:
    bad = {
        "type": "failed",
        "request_id": "r",
        "user_id": 1,
        "model_id": "m",
        "error_kind": "oops",  # invalid kind
        "message": "msg",
    }
    assert try_decode_event(encode_event(bad)) is None
