from __future__ import annotations

import json

from src.clubbot.services.jobs.digits_events import try_decode_event


def test_decode_batch_valid_complete_payload() -> None:
    payload = json.dumps(
        {
            "type": "digits.train.batch.v1",
            "request_id": "r1",
            "user_id": 42,
            "model_id": "mnist",
            "run_id": "run123",
            "ts": "2025-01-01T00:00:00Z",
            "epoch": 2,
            "total_epochs": 10,
            "batch": 100,
            "total_batches": 469,
            "batch_loss": 0.234,
            "batch_acc": 0.912,
            "avg_loss": 0.198,
            "samples_per_sec": 1234.5,
            "main_rss_mb": 512,
            "workers_rss_mb": 256,
            "worker_count": 4,
            "cgroup_usage_mb": 1024,
            "cgroup_limit_mb": 2048,
            "cgroup_pct": 50.0,
            "anon_mb": 768,
            "file_mb": 256,
        }
    )
    evt = try_decode_event(payload)
    assert evt is not None
    assert evt["type"] == "digits.train.batch.v1"
    assert evt["request_id"] == "r1"
    assert evt["user_id"] == 42
    assert evt["model_id"] == "mnist"
    assert evt["run_id"] == "run123"
    assert evt["epoch"] == 2
    assert evt["total_epochs"] == 10
    assert evt["batch"] == 100
    assert evt["total_batches"] == 469
    assert evt["batch_loss"] == 0.234
    assert evt["batch_acc"] == 0.912
    assert evt["avg_loss"] == 0.198
    assert evt["samples_per_sec"] == 1234.5
    assert evt["main_rss_mb"] == 512
    assert evt["workers_rss_mb"] == 256
    assert evt["worker_count"] == 4
    assert evt["cgroup_usage_mb"] == 1024
    assert evt["cgroup_limit_mb"] == 2048
    assert evt["cgroup_pct"] == 50.0
    assert evt["anon_mb"] == 768
    assert evt["file_mb"] == 256


def test_decode_batch_with_null_run_id() -> None:
    payload = json.dumps(
        {
            "type": "digits.train.batch.v1",
            "request_id": "r2",
            "user_id": 1,
            "model_id": "m",
            "run_id": None,
            "ts": "t",
            "epoch": 1,
            "total_epochs": 5,
            "batch": 1,
            "total_batches": 100,
            "batch_loss": 1.0,
            "batch_acc": 0.5,
            "avg_loss": 1.1,
            "samples_per_sec": 100.0,
            "main_rss_mb": 100,
            "workers_rss_mb": 50,
            "worker_count": 2,
            "cgroup_usage_mb": 200,
            "cgroup_limit_mb": 1024,
            "cgroup_pct": 19.5,
            "anon_mb": 150,
            "file_mb": 50,
        }
    )
    evt = try_decode_event(payload)
    assert evt is not None
    assert evt["type"] == "digits.train.batch.v1"
    assert evt["run_id"] is None


def test_decode_batch_missing_batch_field() -> None:
    payload = json.dumps(
        {
            "type": "digits.train.batch.v1",
            "request_id": "r",
            "user_id": 1,
            "model_id": "m",
            "run_id": None,
            "ts": "t",
            "epoch": 1,
            "total_epochs": 5,
            # missing batch
            "total_batches": 100,
            "batch_loss": 1.0,
            "batch_acc": 0.5,
            "avg_loss": 1.1,
            "samples_per_sec": 100.0,
            "main_rss_mb": 100,
            "workers_rss_mb": 50,
            "worker_count": 2,
            "cgroup_usage_mb": 200,
            "cgroup_limit_mb": 1024,
            "cgroup_pct": 19.5,
            "anon_mb": 150,
            "file_mb": 50,
        }
    )
    assert try_decode_event(payload) is None


def test_decode_batch_missing_total_batches_field() -> None:
    payload = json.dumps(
        {
            "type": "digits.train.batch.v1",
            "request_id": "r",
            "user_id": 1,
            "model_id": "m",
            "run_id": None,
            "ts": "t",
            "epoch": 1,
            "total_epochs": 5,
            "batch": 100,
            # missing total_batches
            "batch_loss": 1.0,
            "batch_acc": 0.5,
            "avg_loss": 1.1,
            "samples_per_sec": 100.0,
            "main_rss_mb": 100,
            "workers_rss_mb": 50,
            "worker_count": 2,
            "cgroup_usage_mb": 200,
            "cgroup_limit_mb": 1024,
            "cgroup_pct": 19.5,
            "anon_mb": 150,
            "file_mb": 50,
        }
    )
    assert try_decode_event(payload) is None


def test_decode_batch_batch_field_wrong_type() -> None:
    payload = json.dumps(
        {
            "type": "digits.train.batch.v1",
            "request_id": "r",
            "user_id": 1,
            "model_id": "m",
            "run_id": None,
            "ts": "t",
            "epoch": 1,
            "total_epochs": 5,
            "batch": "100",  # string instead of int
            "total_batches": 100,
            "batch_loss": 1.0,
            "batch_acc": 0.5,
            "avg_loss": 1.1,
            "samples_per_sec": 100.0,
            "main_rss_mb": 100,
            "workers_rss_mb": 50,
            "worker_count": 2,
            "cgroup_usage_mb": 200,
            "cgroup_limit_mb": 1024,
            "cgroup_pct": 19.5,
            "anon_mb": 150,
            "file_mb": 50,
        }
    )
    assert try_decode_event(payload) is None


def test_decode_batch_batch_loss_wrong_type() -> None:
    payload = json.dumps(
        {
            "type": "digits.train.batch.v1",
            "request_id": "r",
            "user_id": 1,
            "model_id": "m",
            "run_id": None,
            "ts": "t",
            "epoch": 1,
            "total_epochs": 5,
            "batch": 100,
            "total_batches": 100,
            "batch_loss": "1.0",  # string instead of float
            "batch_acc": 0.5,
            "avg_loss": 1.1,
            "samples_per_sec": 100.0,
            "main_rss_mb": 100,
            "workers_rss_mb": 50,
            "worker_count": 2,
            "cgroup_usage_mb": 200,
            "cgroup_limit_mb": 1024,
            "cgroup_pct": 19.5,
            "anon_mb": 150,
            "file_mb": 50,
        }
    )
    assert try_decode_event(payload) is None


def test_decode_batch_accepts_int_for_float_fields() -> None:
    payload = json.dumps(
        {
            "type": "digits.train.batch.v1",
            "request_id": "r",
            "user_id": 1,
            "model_id": "m",
            "run_id": None,
            "ts": "t",
            "epoch": 1,
            "total_epochs": 5,
            "batch": 1,
            "total_batches": 100,
            "batch_loss": 1,  # int coerced to float
            "batch_acc": 0,  # int coerced to float
            "avg_loss": 2,  # int coerced to float
            "samples_per_sec": 100,  # int coerced to float
            "main_rss_mb": 100,
            "workers_rss_mb": 50,
            "worker_count": 2,
            "cgroup_usage_mb": 200,
            "cgroup_limit_mb": 1024,
            "cgroup_pct": 19,  # int coerced to float
            "anon_mb": 150,
            "file_mb": 50,
        }
    )
    evt = try_decode_event(payload)
    assert evt is not None
    assert evt["batch_loss"] == 1.0
    assert evt["batch_acc"] == 0.0
    assert evt["avg_loss"] == 2.0
    assert evt["samples_per_sec"] == 100.0
    assert evt["cgroup_pct"] == 19.0


def test_decode_batch_missing_main_rss_mb_field() -> None:
    """Test that missing main_rss_mb field causes decode failure."""
    payload = json.dumps(
        {
            "type": "digits.train.batch.v1",
            "request_id": "r",
            "user_id": 1,
            "model_id": "m",
            "run_id": None,
            "ts": "t",
            "epoch": 1,
            "total_epochs": 5,
            "batch": 1,
            "total_batches": 100,
            "batch_loss": 1.0,
            "batch_acc": 0.5,
            "avg_loss": 1.1,
            "samples_per_sec": 100.0,
            # missing main_rss_mb
            "workers_rss_mb": 50,
            "worker_count": 2,
            "cgroup_usage_mb": 200,
            "cgroup_limit_mb": 1024,
            "cgroup_pct": 19.5,
            "anon_mb": 150,
            "file_mb": 50,
        }
    )
    assert try_decode_event(payload) is None


def test_decode_batch_missing_cgroup_pct_field() -> None:
    """Test that missing cgroup_pct field causes decode failure."""
    payload = json.dumps(
        {
            "type": "digits.train.batch.v1",
            "request_id": "r",
            "user_id": 1,
            "model_id": "m",
            "run_id": None,
            "ts": "t",
            "epoch": 1,
            "total_epochs": 5,
            "batch": 1,
            "total_batches": 100,
            "batch_loss": 1.0,
            "batch_acc": 0.5,
            "avg_loss": 1.1,
            "samples_per_sec": 100.0,
            "main_rss_mb": 100,
            "workers_rss_mb": 50,
            "worker_count": 2,
            "cgroup_usage_mb": 200,
            "cgroup_limit_mb": 1024,
            # missing cgroup_pct
            "anon_mb": 150,
            "file_mb": 50,
        }
    )
    assert try_decode_event(payload) is None


def test_decode_batch_main_rss_mb_wrong_type() -> None:
    """Test that string value for main_rss_mb causes decode failure."""
    payload = json.dumps(
        {
            "type": "digits.train.batch.v1",
            "request_id": "r",
            "user_id": 1,
            "model_id": "m",
            "run_id": None,
            "ts": "t",
            "epoch": 1,
            "total_epochs": 5,
            "batch": 1,
            "total_batches": 100,
            "batch_loss": 1.0,
            "batch_acc": 0.5,
            "avg_loss": 1.1,
            "samples_per_sec": 100.0,
            "main_rss_mb": "100",  # string instead of int
            "workers_rss_mb": 50,
            "worker_count": 2,
            "cgroup_usage_mb": 200,
            "cgroup_limit_mb": 1024,
            "cgroup_pct": 19.5,
            "anon_mb": 150,
            "file_mb": 50,
        }
    )
    assert try_decode_event(payload) is None


def test_decode_batch_cgroup_pct_wrong_type() -> None:
    """Test that string value for cgroup_pct causes decode failure."""
    payload = json.dumps(
        {
            "type": "digits.train.batch.v1",
            "request_id": "r",
            "user_id": 1,
            "model_id": "m",
            "run_id": None,
            "ts": "t",
            "epoch": 1,
            "total_epochs": 5,
            "batch": 1,
            "total_batches": 100,
            "batch_loss": 1.0,
            "batch_acc": 0.5,
            "avg_loss": 1.1,
            "samples_per_sec": 100.0,
            "main_rss_mb": 100,
            "workers_rss_mb": 50,
            "worker_count": 2,
            "cgroup_usage_mb": 200,
            "cgroup_limit_mb": 1024,
            "cgroup_pct": "19.5",  # string instead of float
            "anon_mb": 150,
            "file_mb": 50,
        }
    )
    assert try_decode_event(payload) is None


def test_decode_best_valid_complete_payload() -> None:
    payload = json.dumps(
        {
            "type": "digits.train.best.v1",
            "request_id": "r1",
            "user_id": 42,
            "model_id": "mnist",
            "run_id": "run123",
            "ts": "2025-01-01T00:00:00Z",
            "epoch": 3,
            "val_acc": 0.956,
        }
    )
    evt = try_decode_event(payload)
    assert evt is not None
    assert evt["type"] == "digits.train.best.v1"
    assert evt["request_id"] == "r1"
    assert evt["user_id"] == 42
    assert evt["model_id"] == "mnist"
    assert evt["run_id"] == "run123"
    assert evt["epoch"] == 3
    assert evt["val_acc"] == 0.956


def test_decode_best_with_null_run_id() -> None:
    payload = json.dumps(
        {
            "type": "digits.train.best.v1",
            "request_id": "r",
            "user_id": 1,
            "model_id": "m",
            "run_id": None,
            "ts": "t",
            "epoch": 1,
            "val_acc": 0.9,
        }
    )
    evt = try_decode_event(payload)
    assert evt is not None
    assert evt["type"] == "digits.train.best.v1"
    assert evt["run_id"] is None


def test_decode_best_missing_epoch_field() -> None:
    payload = json.dumps(
        {
            "type": "digits.train.best.v1",
            "request_id": "r",
            "user_id": 1,
            "model_id": "m",
            "run_id": None,
            "ts": "t",
            # missing epoch
            "val_acc": 0.9,
        }
    )
    assert try_decode_event(payload) is None


def test_decode_best_missing_val_acc_field() -> None:
    payload = json.dumps(
        {
            "type": "digits.train.best.v1",
            "request_id": "r",
            "user_id": 1,
            "model_id": "m",
            "run_id": None,
            "ts": "t",
            "epoch": 1,
            # missing val_acc
        }
    )
    assert try_decode_event(payload) is None


def test_decode_best_val_acc_wrong_type() -> None:
    payload = json.dumps(
        {
            "type": "digits.train.best.v1",
            "request_id": "r",
            "user_id": 1,
            "model_id": "m",
            "run_id": None,
            "ts": "t",
            "epoch": 1,
            "val_acc": "0.9",  # string instead of float
        }
    )
    assert try_decode_event(payload) is None


def test_decode_best_accepts_int_for_val_acc() -> None:
    payload = json.dumps(
        {
            "type": "digits.train.best.v1",
            "request_id": "r",
            "user_id": 1,
            "model_id": "m",
            "run_id": None,
            "ts": "t",
            "epoch": 1,
            "val_acc": 1,  # int coerced to float
        }
    )
    evt = try_decode_event(payload)
    assert evt is not None
    assert evt["val_acc"] == 1.0
