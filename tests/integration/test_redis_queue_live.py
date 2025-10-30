from __future__ import annotations

import asyncio
import os
import time

import pytest
import src.clubbot.services.jobs.queue as queue_mod
from src.clubbot.services.jobs.queue import RedisJobQueue, TranscriptJob


@pytest.mark.asyncio
async def test_redis_enqueue_pop_round_trip_with_live_or_fake(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = (os.getenv("REDIS_URL") or "").strip()
    if not url:

        class _FakeRedisClient:
            def __init__(self) -> None:
                self._list: list[str] = []

            async def brpop(
                self, name: str, timeout: int | None = None, **_kwargs: object
            ) -> tuple[str, str] | None:
                deadline = time.monotonic() + (float(timeout) if timeout else 1.0)
                while time.monotonic() < deadline:
                    if self._list:
                        value = self._list.pop()
                        return name, value
                    await asyncio.sleep(0.01)
                return None

            async def lpush(self, _name: str, value: str) -> int:
                self._list.insert(0, value)
                return len(self._list)

        fake = _FakeRedisClient()

        def fake_from_url(_url: str) -> _FakeRedisClient:
            return fake

        monkeypatch.setattr(queue_mod, "_redis_from_url", fake_from_url)
        url = "redis://fake"

    q = RedisJobQueue(url=url)
    job = TranscriptJob(request_id="it-req-1", url="https://example.com", user_id=7)

    async def pop_task() -> TranscriptJob | None:
        return await asyncio.wait_for(q.pop(), timeout=3.0)

    t = asyncio.create_task(pop_task())
    await asyncio.sleep(0.05)
    await q.enqueue(job)
    out = await t
    assert isinstance(out, TranscriptJob)
    assert out.request_id == job.request_id
