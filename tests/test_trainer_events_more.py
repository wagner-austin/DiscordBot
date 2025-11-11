from __future__ import annotations

import json

from clubbot.services.jobs.trainer_events import StartedV1, encode_event, try_decode_event


def test_started_with_optional_fields_decodes() -> None:
    ev: StartedV1 = {
        "type": "trainer.train.started.v1",
        "request_id": "r",
        "run_id": "run",
        "user_id": 1,
        "model_family": "gpt2",
        "model_size": "small",
        "total_epochs": 3,
        "queue": "training",
        "cpu_cores": 8,
        "memory_mb": 2048,
        "optimal_threads": 4,
        "optimal_workers": 2,
        "batch_size": 2,
        "learning_rate": 5e-4,
    }
    out = try_decode_event(encode_event(ev))
    assert out is not None and out.get("optimal_threads") == 4


def test_invalid_payload_returns_none() -> None:
    assert try_decode_event("not json") is None
    assert try_decode_event("[]") is None
    bad = json.dumps({"type": "trainer.train.started.v1"})
    assert try_decode_event(bad) is None
