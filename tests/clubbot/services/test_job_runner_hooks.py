from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest
from src.clubbot.services.jobs.helpers import (
    default_retry_policy_factory,
    failure_notifier_factory,
)
from src.clubbot.services.jobs.queue import JobBase, MemoryJobQueue
from src.clubbot.services.jobs.runner import JobRunner
from src.clubbot.utils.errors import UserInputError


@dataclass(frozen=True)
class FakeJob(JobBase):
    request_id: str
    user_id: int


@pytest.mark.asyncio
async def test_user_error_not_retried_and_notified_once() -> None:
    q: MemoryJobQueue[FakeJob] = MemoryJobQueue()
    notifications: list[tuple[int, str]] = []

    async def notify(uid: int, msg: str) -> None:
        notifications.append((uid, msg))

    runner = JobRunner[FakeJob](
        queue=q,
        handler=lambda job: (_ for _ in ()).throw(UserInputError("bad input")),
        failure_callback=failure_notifier_factory(notify_fn=notify, service_name="test"),
        retry_policy=default_retry_policy_factory(UserInputError),
        retry_attempts=1,
        retry_backoff=0.01,
        poll_interval=0.01,
    )
    runner.start()
    await q.enqueue(FakeJob(request_id="r1", user_id=99))
    await asyncio.sleep(0.05)
    await runner.stop()

    assert len(notifications) == 1
    uid, msg = notifications[0]
    assert uid == 99
    assert "failed" in msg.lower() and "bad input" in msg


@pytest.mark.asyncio
async def test_system_error_notified_on_final_failure_only() -> None:
    q: MemoryJobQueue[FakeJob] = MemoryJobQueue()
    notifications: list[tuple[int, str]] = []

    async def notify(uid: int, msg: str) -> None:
        notifications.append((uid, msg))

    async def handler(job: FakeJob) -> None:
        raise RuntimeError("boom")

    runner = JobRunner[FakeJob](
        queue=q,
        handler=handler,
        failure_callback=failure_notifier_factory(notify_fn=notify, service_name="test"),
        # No retry policy: will retry once (retry_attempts=1), then notify on final failure
        retry_attempts=1,
        retry_backoff=0.01,
        poll_interval=0.01,
    )
    runner.start()
    await q.enqueue(FakeJob(request_id="r2", user_id=7))
    await asyncio.sleep(0.08)
    await runner.stop()

    # Only one notification on final failure (not on first attempt)
    assert len(notifications) == 1
    uid, msg = notifications[0]
    assert uid == 7
    assert "error" in msg.lower() or "failed" in msg.lower()
