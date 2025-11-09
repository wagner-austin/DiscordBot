from __future__ import annotations

import json

from src.clubbot.services.jobs.digits_events import try_decode_event


def test_decode_artifact_valid_complete_payload() -> None:
    payload = json.dumps(
        {
            "type": "digits.train.artifact.v1",
            "request_id": "r1",
            "user_id": 42,
            "model_id": "mnist",
            "run_id": "2025-01-01T12:00:00",
            "ts": "2025-01-01T12:00:00Z",
            "path": "/artifacts/digits/models/mnist_resnet18_v1",
        }
    )
    evt = try_decode_event(payload)
    assert evt is not None
    assert evt["type"] == "digits.train.artifact.v1"
    assert evt["request_id"] == "r1"
    assert evt["user_id"] == 42
    assert evt["model_id"] == "mnist"
    assert evt["run_id"] == "2025-01-01T12:00:00"
    assert evt["path"] == "/artifacts/digits/models/mnist_resnet18_v1"


def test_decode_artifact_with_null_run_id() -> None:
    payload = json.dumps(
        {
            "type": "digits.train.artifact.v1",
            "request_id": "r2",
            "user_id": 1,
            "model_id": "m",
            "run_id": None,
            "ts": "t",
            "path": "/path/to/artifact",
        }
    )
    evt = try_decode_event(payload)
    assert evt is not None
    assert evt["type"] == "digits.train.artifact.v1"
    assert evt["run_id"] is None


def test_decode_artifact_missing_path_field() -> None:
    payload = json.dumps(
        {
            "type": "digits.train.artifact.v1",
            "request_id": "r",
            "user_id": 1,
            "model_id": "m",
            "run_id": None,
            "ts": "t",
            # missing path
        }
    )
    assert try_decode_event(payload) is None


def test_decode_artifact_path_wrong_type() -> None:
    payload = json.dumps(
        {
            "type": "digits.train.artifact.v1",
            "request_id": "r",
            "user_id": 1,
            "model_id": "m",
            "run_id": None,
            "ts": "t",
            "path": 123,  # int instead of string
        }
    )
    assert try_decode_event(payload) is None


def test_decode_upload_valid_complete_payload() -> None:
    payload = json.dumps(
        {
            "type": "digits.train.upload.v1",
            "request_id": "r1",
            "user_id": 42,
            "model_id": "mnist",
            "run_id": "2025-01-01T12:00:00",
            "ts": "2025-01-01T12:05:00Z",
            "status": 200,
            "model_bytes": 45678901,
            "manifest_bytes": 1234,
        }
    )
    evt = try_decode_event(payload)
    assert evt is not None
    assert evt["type"] == "digits.train.upload.v1"
    assert evt["request_id"] == "r1"
    assert evt["user_id"] == 42
    assert evt["model_id"] == "mnist"
    assert evt["run_id"] == "2025-01-01T12:00:00"
    assert evt["status"] == 200
    assert evt["model_bytes"] == 45678901
    assert evt["manifest_bytes"] == 1234


def test_decode_upload_with_null_run_id() -> None:
    payload = json.dumps(
        {
            "type": "digits.train.upload.v1",
            "request_id": "r2",
            "user_id": 1,
            "model_id": "m",
            "run_id": None,
            "ts": "t",
            "status": 500,
            "model_bytes": 100,
            "manifest_bytes": 50,
        }
    )
    evt = try_decode_event(payload)
    assert evt is not None
    assert evt["type"] == "digits.train.upload.v1"
    assert evt["run_id"] is None


def test_decode_upload_missing_status_field() -> None:
    payload = json.dumps(
        {
            "type": "digits.train.upload.v1",
            "request_id": "r",
            "user_id": 1,
            "model_id": "m",
            "run_id": None,
            "ts": "t",
            # missing status
            "model_bytes": 100,
            "manifest_bytes": 50,
        }
    )
    assert try_decode_event(payload) is None


def test_decode_upload_status_wrong_type() -> None:
    payload = json.dumps(
        {
            "type": "digits.train.upload.v1",
            "request_id": "r",
            "user_id": 1,
            "model_id": "m",
            "run_id": None,
            "ts": "t",
            "status": "200",  # string instead of int
            "model_bytes": 100,
            "manifest_bytes": 50,
        }
    )
    assert try_decode_event(payload) is None


def test_decode_upload_model_bytes_wrong_type() -> None:
    payload = json.dumps(
        {
            "type": "digits.train.upload.v1",
            "request_id": "r",
            "user_id": 1,
            "model_id": "m",
            "run_id": None,
            "ts": "t",
            "status": 200,
            "model_bytes": "100",  # string instead of int
            "manifest_bytes": 50,
        }
    )
    assert try_decode_event(payload) is None


def test_decode_prune_valid_complete_payload() -> None:
    payload = json.dumps(
        {
            "type": "digits.train.prune.v1",
            "request_id": "r1",
            "user_id": 42,
            "model_id": "mnist",
            "run_id": "2025-01-01T12:00:00",
            "ts": "2025-01-01T12:10:00Z",
            "deleted_count": 3,
        }
    )
    evt = try_decode_event(payload)
    assert evt is not None
    assert evt["type"] == "digits.train.prune.v1"
    assert evt["request_id"] == "r1"
    assert evt["user_id"] == 42
    assert evt["model_id"] == "mnist"
    assert evt["run_id"] == "2025-01-01T12:00:00"
    assert evt["deleted_count"] == 3


def test_decode_prune_with_null_run_id() -> None:
    payload = json.dumps(
        {
            "type": "digits.train.prune.v1",
            "request_id": "r2",
            "user_id": 1,
            "model_id": "m",
            "run_id": None,
            "ts": "t",
            "deleted_count": 0,
        }
    )
    evt = try_decode_event(payload)
    assert evt is not None
    assert evt["type"] == "digits.train.prune.v1"
    assert evt["run_id"] is None


def test_decode_prune_missing_deleted_count_field() -> None:
    payload = json.dumps(
        {
            "type": "digits.train.prune.v1",
            "request_id": "r",
            "user_id": 1,
            "model_id": "m",
            "run_id": None,
            "ts": "t",
            # missing deleted_count
        }
    )
    assert try_decode_event(payload) is None


def test_decode_prune_deleted_count_wrong_type() -> None:
    payload = json.dumps(
        {
            "type": "digits.train.prune.v1",
            "request_id": "r",
            "user_id": 1,
            "model_id": "m",
            "run_id": None,
            "ts": "t",
            "deleted_count": "3",  # string instead of int
        }
    )
    assert try_decode_event(payload) is None
