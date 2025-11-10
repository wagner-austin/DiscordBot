from __future__ import annotations

import json

from src.clubbot.services.jobs.digits_events import try_decode_event


def test_decode_started_includes_augment_and_batch() -> None:
    payload = {
        "type": "digits.train.started.v1",
        "request_id": "r",
        "user_id": 1,
        "model_id": "m",
        "run_id": None,
        "ts": "t",
        "total_epochs": 2,
        "queue": "digits",
        # Optional rich context
        "cpu_cores": 2,
        "optimal_threads": 2,
        "memory_mb": 953,
        "optimal_workers": 0,
        "max_batch_size": 64,
        "device": "cpu",
        # Training config and augmentation
        "batch_size": 64,
        "augment": True,
        "aug_rotate": 10.0,
        "aug_translate": 0.1,
        "noise_prob": 0.2,
        "dots_prob": 0.1,
    }
    ev = try_decode_event(json.dumps(payload))
    assert ev is not None
    assert ev["type"] == "digits.train.started.v1"
    # Ensure augmentation details are preserved
    assert ev.get("batch_size") == 64
    assert ev.get("augment") is True
    assert ev.get("aug_rotate") == 10.0
    assert ev.get("aug_translate") == 0.1
    assert ev.get("noise_prob") == 0.2
    assert ev.get("dots_prob") == 0.1


def test_decode_started_omits_unknown_optionals() -> None:
    payload = {
        "type": "digits.train.started.v1",
        "request_id": "r",
        "user_id": 1,
        "model_id": "m",
        "run_id": None,
        "ts": "t",
        "total_epochs": 1,
        "queue": "digits",
    }
    ev = try_decode_event(json.dumps(payload))
    assert ev is not None
    # None of these should be present when not sent by producer
    for k in (
        "batch_size",
        "augment",
        "aug_rotate",
        "aug_translate",
        "noise_prob",
        "dots_prob",
        "device",
        "cpu_cores",
        "memory_mb",
        "optimal_threads",
        "optimal_workers",
        "max_batch_size",
    ):
        assert k not in ev


def test_decode_started_learning_rate_as_int() -> None:
    """Test that learning_rate as int is converted to float."""
    payload = {
        "type": "digits.train.started.v1",
        "request_id": "r",
        "user_id": 1,
        "model_id": "m",
        "run_id": None,
        "ts": "t",
        "total_epochs": 1,
        "queue": "digits",
        "learning_rate": 1,  # int instead of float
    }
    ev = try_decode_event(json.dumps(payload))
    assert ev is not None
    assert ev.get("learning_rate") == 1.0  # Should be converted to float
    assert isinstance(ev.get("learning_rate"), float)
