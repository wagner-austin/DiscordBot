from __future__ import annotations

from types import SimpleNamespace

import pytest
from src.clubbot.services.jobs.rq_enqueuer import RQTranscriptEnqueuer


class _FakeJob:
    def __init__(self, job_id: str) -> None:
        self._id = job_id

    def get_id(self) -> str:  # pragma: no cover - trivial accessor
        return self._id


class _FakeQueue:
    def __init__(self, name: str, connection: object) -> None:
        self.name = name
        self.connection = connection
        self.last_args: tuple[object, ...] | None = None
        self.last_kwargs: dict[str, object] | None = None

    def enqueue(self, f: str, payload: dict[str, object], **kwargs: object) -> _FakeJob:
        self.last_args = (f, payload)
        self.last_kwargs = dict(kwargs)
        return _FakeJob("job-1")


class _FakeRetry:
    def __init__(self, max: int, interval: list[int]) -> None:
        self.max = max
        self.interval = interval


def test_rq_enqueuer_builds_job_with_expected_args(monkeypatch: pytest.MonkeyPatch) -> None:
    # Monkeypatch rq and redis surfaces
    fake_queue = _FakeQueue("transcript", object())

    def fake_queue_ctor(name: str, connection: object) -> _FakeQueue:
        assert name == "transcript"
        return fake_queue

    # Provide only top-level Retry on rq to assert correct import path
    monkeypatch.setitem(
        __import__("sys").modules,
        "rq",
        SimpleNamespace(Queue=fake_queue_ctor, Retry=_FakeRetry),
    )

    class _FakeRedis:
        @staticmethod
        def from_url(url: str, decode_responses: bool = False) -> object:
            assert decode_responses is False  # RQ requires binary mode
            assert url == "redis://fake"
            return object()

    monkeypatch.setitem(__import__("sys").modules, "redis", _FakeRedis)

    enq = RQTranscriptEnqueuer(
        redis_url="redis://fake",
        job_timeout_s=123,
        result_ttl_s=456,
        failure_ttl_s=789,
        retry_max=3,
        retry_intervals_s=(1, 2),
    )
    job_id = enq.enqueue_transcript(request_id="r1", url="https://x", user_id=7)
    assert job_id == "job-1"

    # Validate payload and config captured by fake queue
    assert fake_queue.last_args is not None
    fpath, payload = fake_queue.last_args
    assert fpath == "clubbot.workers.transcript.process_transcript_job"
    assert isinstance(payload, dict) and payload["request_id"] == "r1" and payload["user_id"] == 7
    assert fake_queue.last_kwargs is not None
    assert fake_queue.last_kwargs["job_timeout"] == 123
    assert fake_queue.last_kwargs["result_ttl"] == 456
    assert fake_queue.last_kwargs["failure_ttl"] == 789
