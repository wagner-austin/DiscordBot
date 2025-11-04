from __future__ import annotations

import types

from src.clubbot.services.jobs.digits_enqueuer import RQDigitsEnqueuer


def test_digits_enqueuer_builds_job_with_expected_args(monkeypatch) -> None:
    calls: dict[str, object] = {}

    class _Job:
        def __init__(self, jid: str) -> None:
            self._id = jid

        def get_id(self) -> str:  # pragma: no cover - trivial passthrough
            return self._id

    class _Queue:
        def __init__(self, name: str, connection: object | None = None) -> None:
            calls["queue_name"] = name

        def enqueue(self, func_name: str, payload: dict[str, object], **opts: object) -> _Job:
            calls["func_name"] = func_name
            calls["payload"] = payload
            calls["opts"] = opts
            return _Job("jid1")

    def _fake_from_url(_: str) -> object:
        return object()

    monkeypatch.setattr("src.clubbot.services.jobs.digits_enqueuer._redis_from_url", _fake_from_url)
    # Inject an rq module stub with Queue/Retry
    import sys

    prev = sys.modules.get("rq")
    sys.modules["rq"] = types.ModuleType("rq")
    sys.modules["rq"].Queue = _Queue

    class _Retry:
        def __init__(self, **_: object) -> None:
            pass

    sys.modules["rq"].Retry = _Retry

    enq = RQDigitsEnqueuer(redis_url="redis://localhost:6379/0")
    job_id = enq.enqueue_train(
        request_id="r1",
        user_id=9,
        model_id="m",
        epochs=5,
        batch_size=32,
        lr=0.001,
        seed=42,
        augment=True,
        notes="hello",
    )
    assert job_id == "jid1"
    assert calls["queue_name"] == "digits"
    assert calls["func_name"] == "handwriting_ai.jobs.digits.process_train_job"
    payload = calls["payload"]
    assert isinstance(payload, dict)
    assert payload["type"] == "digits.train.v1"
    assert payload["request_id"] == "r1"
    assert payload["user_id"] == 9
    assert payload["model_id"] == "m"
    assert payload["epochs"] == 5
    assert payload["batch_size"] == 32
    assert payload["lr"] == 0.001
    assert payload["seed"] == 42
    assert payload["augment"] is True
    # Restore rq module to avoid affecting other tests
    if prev is not None:
        sys.modules["rq"] = prev
    else:
        del sys.modules["rq"]
