from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest
import src.clubbot.services.jobs.queue as queue_mod
from src.clubbot.services.jobs.queue import RedisJobQueue, TranscriptJob


@dataclass(frozen=True)
class _FakeRedisClient:
    name: str
    _list: list[str]

    async def brpop(
        self, _name: str, timeout: int | None = None, **_kwargs: object
    ) -> tuple[str, str] | None:
        _ = timeout  # satisfy linters; behavior does not depend on timeout in fake
        if self._list:
            value = self._list.pop()
            return self.name, value
        # Simulate a short blocking wait and timeout
        await asyncio.sleep(0.01)
        return None

    async def lpush(self, _name: str, value: str) -> int:
        self._list.insert(0, value)
        return len(self._list)


@pytest.mark.asyncio
async def test_redis_queue_enqueue_and_pop_with_fake_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeRedisClient(name="transcript:jobs", _list=[])

    def fake_from_url(_url: str) -> _FakeRedisClient:
        return fake

    monkeypatch.setattr(queue_mod, "_redis_from_url", fake_from_url)

    q = RedisJobQueue(url="redis://fake")
    job = TranscriptJob(request_id="req-1", url="https://x", user_id=42)
    await q.enqueue(job)
    out = await q.pop()
    assert isinstance(out, TranscriptJob)
    assert out.request_id == job.request_id
    assert out.user_id == job.user_id
    assert out.url == job.url


@pytest.mark.asyncio
async def test_redis_queue_pop_empty_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeRedisClient(name="transcript:jobs", _list=[])

    def fake_from_url(_url: str) -> _FakeRedisClient:
        return fake

    monkeypatch.setattr(queue_mod, "_redis_from_url", fake_from_url)

    q = RedisJobQueue(url="redis://fake")
    out = await q.pop()
    assert out is None
