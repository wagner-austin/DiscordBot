from __future__ import annotations

import pytest
from src.clubbot.services.jobs.digits_events import (
    DEFAULT_DIGITS_EVENTS_CHANNEL,
    encode_event,
    try_decode_event,
)


def test_digits_events_encode_decode_roundtrip() -> None:
    started = {
        "type": "digits.train.started.v1",
        "request_id": "r1",
        "user_id": 1,
        "model_id": "m",
        "run_id": None,
        "ts": "2025-01-01T00:00:00+00:00",
        "total_epochs": 10,
        # Optional extras should round-trip when present
        "cpu_cores": 2,
        "optimal_threads": 2,
        "memory_mb": 953,
        "optimal_workers": 0,
        "max_batch_size": 64,
        "device": "cpu",
    }
    s = encode_event(started)  # should be JSON
    evt = try_decode_event(s)
    assert evt is not None and evt["type"] == "digits.train.started.v1"
    assert DEFAULT_DIGITS_EVENTS_CHANNEL == "digits:events"
    assert evt.get("cpu_cores") == 2
    assert evt.get("memory_mb") == 953
    assert evt.get("max_batch_size") == 64
    assert evt.get("device") == "cpu"

    progress = {
        "type": "digits.train.epoch.v1",
        "request_id": "r1",
        "user_id": 1,
        "model_id": "m",
        "run_id": None,
        "ts": "2025-01-01T00:00:00+00:00",
        "epoch": 3,
        "total_epochs": 10,
        "train_loss": 0.1,
        "val_acc": 0.95,
        "time_s": 1.2,
    }
    s2 = encode_event(progress)
    evt2 = try_decode_event(s2)
    assert evt2 is not None and evt2["type"] == "digits.train.epoch.v1"

    completed = {
        "type": "digits.train.completed.v1",
        "request_id": "r1",
        "user_id": 1,
        "model_id": "m",
        "run_id": None,
        "ts": "2025-01-01T00:00:00+00:00",
        "val_acc": 0.97,
    }
    s3 = encode_event(completed)
    evt3 = try_decode_event(s3)
    assert evt3 is not None and evt3["type"] == "digits.train.completed.v1"

    failed = {
        "type": "digits.train.failed.v1",
        "request_id": "r1",
        "user_id": 1,
        "model_id": "m",
        "run_id": None,
        "ts": "2025-01-01T00:00:00+00:00",
        "error_kind": "system",
        "message": "boom",
    }
    s4 = encode_event(failed)
    evt4 = try_decode_event(s4)
    assert evt4 is not None and evt4["type"] == "digits.train.failed.v1"


def test_digits_events_decode_started_without_extras() -> None:
    import json as _json

    payload = _json.dumps(
        {
            "type": "digits.train.started.v1",
            "request_id": "r",
            "user_id": 1,
            "model_id": "m",
            "run_id": None,
            "ts": "t",
            "total_epochs": 5,
        }
    )
    evt = try_decode_event(payload)
    assert evt is not None and "cpu_cores" not in evt and "max_batch_size" not in evt


def test_digits_events_decode_invalid_json_and_non_dict() -> None:
    assert try_decode_event("not json") is None
    assert try_decode_event("[]") is None


def test_digits_events_decode_started_missing_fields() -> None:
    bad = {"type": "digits.train.started.v1", "request_id": "r", "user_id": 1, "model_id": "m"}
    assert try_decode_event(encode_event(bad)) is None


def test_digits_events_decode_progress_invalid_types() -> None:
    bad = {
        "type": "digits.train.epoch.v1",
        "request_id": "r",
        "user_id": 1,
        "model_id": "m",
        "epoch": "3",  # wrong type
        "total_epochs": 10,
        "train_loss": 0.1,
        "val_acc": 0.5,
        "time_s": 1.0,
        "ts": "t",
        "run_id": None,
    }
    assert try_decode_event(encode_event(bad)) is None


def test_digits_events_decode_completed_invalid_types() -> None:
    bad = {
        "type": "digits.train.completed.v1",
        "request_id": "r",
        "user_id": 1,
        "model_id": "m",
        "run_id": None,
        "ts": "t",
        "val_acc": "0.95",  # wrong type
    }
    assert try_decode_event(encode_event(bad)) is None


def test_digits_events_decode_unknown_type() -> None:
    unknown = {"type": "foo", "request_id": "r", "user_id": 1, "model_id": "m"}
    assert try_decode_event(encode_event(unknown)) is None


def test_digits_events_decode_missing_type_or_nonstring() -> None:
    import json as _json

    assert try_decode_event(_json.dumps({})) is None
    assert try_decode_event(_json.dumps({"type": 123})) is None


def test_digits_events_decode_failed_invalid_types() -> None:
    bad = {
        "type": "digits.train.failed.v1",
        "request_id": "r",
        "user_id": 1,
        "model_id": "m",
        "run_id": None,
        "ts": "t",
        "error_kind": "oops",  # invalid kind
        "message": "msg",
    }
    assert try_decode_event(encode_event(bad)) is None


def test_parse_json_obj_drops_non_string_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    import json as _json

    import src.clubbot.services.jobs.digits_events as mod

    # Monkeypatch json.loads to return a dict with a non-string key
    def _fake_loads(_s: str) -> dict[object, object]:
        return {1: "x", "type": "digits.train.completed.v1"}

    monkeypatch.setattr(_json, "loads", _fake_loads, raising=True)
    # Unknown/incomplete payload should return None, exercising non-string key branch
    assert mod.try_decode_event("{}") is None
