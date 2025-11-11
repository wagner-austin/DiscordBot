from __future__ import annotations

from clubbot.services.jobs.trainer_events import (
    CompletedV1,
    FailedV1,
    ProgressV1,
    StartedV1,
    encode_event,
    try_decode_event,
)


def test_decode_started_roundtrip() -> None:
    ev: StartedV1 = {
        "type": "trainer.train.started.v1",
        "request_id": "r1",
        "run_id": "run1",
        "user_id": 123,
        "model_family": "gpt2",
        "model_size": "small",
        "total_epochs": 5,
        "queue": "training",
        "batch_size": 4,
        "learning_rate": 5e-4,
    }
    out = try_decode_event(encode_event(ev))
    assert out is not None and out["type"] == ev["type"] and out["run_id"] == "run1"


def test_decode_progress_roundtrip() -> None:
    ev: ProgressV1 = {
        "type": "trainer.train.progress.v1",
        "request_id": "r1",
        "run_id": "run1",
        "user_id": 123,
        "epoch": 1,
        "total_epochs": 5,
        "step": 10,
        "loss": 1.23,
    }
    out = try_decode_event(encode_event(ev))
    assert out is not None and out["epoch"] == 1 and out["loss"] == 1.23


def test_decode_completed_roundtrip() -> None:
    ev: CompletedV1 = {
        "type": "trainer.train.completed.v1",
        "request_id": "r1",
        "run_id": "run1",
        "user_id": 123,
        "loss": 0.5,
        "perplexity": 2.0,
        "artifact_path": "/data/artifacts/models/run1",
    }
    out = try_decode_event(encode_event(ev))
    assert out is not None and out["artifact_path"].endswith("run1")


def test_decode_failed_roundtrip() -> None:
    ev: FailedV1 = {
        "type": "trainer.train.failed.v1",
        "request_id": "r1",
        "run_id": "run1",
        "user_id": 123,
        "error_kind": "system",
        "message": "oom",
        "status": "failed",
    }
    out = try_decode_event(encode_event(ev))
    assert out is not None and out["status"] == "failed"
