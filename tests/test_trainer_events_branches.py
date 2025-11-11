from __future__ import annotations

import json

from clubbot.services.jobs.trainer_events import try_decode_event


def test_decode_started_minimal_fields() -> None:
    s = json.dumps(
        {
            "type": "trainer.train.started.v1",
            "request_id": "r",
            "run_id": "run",
            "user_id": 1,
            "model_family": "gpt2",
            "model_size": "small",
            "total_epochs": 1,
            "queue": "training",
        }
    )
    out = try_decode_event(s)
    assert out is not None and out["type"] == "trainer.train.started.v1"


def test_decode_progress_float_variants() -> None:
    p = json.dumps(
        {
            "type": "trainer.train.progress.v1",
            "request_id": "r",
            "run_id": "run",
            "user_id": 1,
            "epoch": 1,
            "total_epochs": 2,
            "step": 10,
            "loss": 1,
        }
    )
    out = try_decode_event(p)
    assert out is not None and isinstance(out["loss"], float)


def test_decode_completed_int_fields() -> None:
    c = json.dumps(
        {
            "type": "trainer.train.completed.v1",
            "request_id": "r",
            "run_id": "run",
            "user_id": 1,
            "loss": 1,
            "perplexity": 2,
            "artifact_path": "/x",
        }
    )
    out = try_decode_event(c)
    assert out is not None and out["artifact_path"] == "/x"


def test_decode_failed_canceled_status() -> None:
    f = json.dumps(
        {
            "type": "trainer.train.failed.v1",
            "request_id": "r",
            "run_id": "run",
            "user_id": 1,
            "error_kind": "user",
            "message": "stop",
            "status": "canceled",
        }
    )
    out = try_decode_event(f)
    assert out is not None and out["status"] == "canceled"


def test_decode_unknown_type_returns_none() -> None:
    u = json.dumps({"type": "trainer.train.unknown", "foo": 1})
    assert try_decode_event(u) is None
