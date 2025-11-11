from __future__ import annotations

import json

from clubbot.services.jobs.trainer_events import try_decode_event


def test_decode_progress_invalid_types_returns_none() -> None:
    bad = json.dumps(
        {
            "type": "trainer.train.progress.v1",
            "request_id": "r",
            "run_id": "run",
            "user_id": 1,
            "epoch": "x",
            "total_epochs": 2,
            "step": 10,
            "loss": 1.0,
        }
    )
    assert try_decode_event(bad) is None


def test_decode_completed_invalid_returns_none() -> None:
    bad = json.dumps(
        {
            "type": "trainer.train.completed.v1",
            "request_id": "r",
            "run_id": "run",
            "user_id": 1,
            "loss": "a",
            "perplexity": 2,
            "artifact_path": "/x",
        }
    )
    assert try_decode_event(bad) is None


def test_decode_failed_invalid_returns_none() -> None:
    bad = json.dumps(
        {
            "type": "trainer.train.failed.v1",
            "request_id": "r",
            "run_id": "run",
            "user_id": 1,
            "error_kind": "oops",
            "message": "stop",
            "status": "failed",
        }
    )
    assert try_decode_event(bad) is None
