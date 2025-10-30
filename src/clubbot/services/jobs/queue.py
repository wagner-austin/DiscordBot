from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Generic, Protocol, TypedDict, TypeVar

# Typed shim for redis client to keep strict typing without casts/ignores.
if TYPE_CHECKING:

    class _RedisClientProto(Protocol):
        async def brpop(self, name: str, timeout: int) -> tuple[str, str] | None: ...
        async def lpush(self, name: str, value: str) -> int: ...

    def _redis_from_url(url: str) -> _RedisClientProto: ...
else:  # pragma: no cover - runtime import only

    def _redis_from_url(url: str):
        import redis.asyncio as redis_asyncio

        return redis_asyncio.from_url(url, encoding="utf-8", decode_responses=True)


class JobBase(Protocol):
    request_id: str
    user_id: int


@dataclass(frozen=True)
class TranscriptJob(JobBase):
    request_id: str
    url: str
    user_id: int
    # Unix timestamp seconds when enqueued; 0.0 if unknown (e.g., tests)
    queued_ts: float = 0.0


T = TypeVar("T", bound=JobBase)


class JobQueueProto(Protocol, Generic[T]):
    async def enqueue(self, job: T) -> None: ...
    async def pop(self) -> T | None: ...
    def is_blocking(self) -> bool: ...


class MemoryJobQueue(Generic[T], JobQueueProto[T]):
    """A simple in-process queue useful for tests and local runs."""

    def __init__(self) -> None:
        self._q: asyncio.Queue[T] = asyncio.Queue()

    async def enqueue(self, job: T) -> None:
        await self._q.put(job)

    async def pop(self) -> T | None:
        try:
            return self._q.get_nowait()
        except asyncio.QueueEmpty:
            return None

    def is_blocking(self) -> bool:
        # In-memory queue does not block; caller should sleep between polls.
        return False


def build_queue(*, brpop_timeout_seconds: int | None = None) -> JobQueueProto[TranscriptJob]:
    url = (os.getenv("REDIS_URL") or "").strip()
    if not url:
        raise RuntimeError("REDIS_URL is required for the queue backend")
    return RedisJobQueue(url=url, brpop_timeout_seconds=brpop_timeout_seconds)


class _JobPayload(TypedDict, total=False):
    request_id: str
    url: str
    user_id: int
    queued_ts: float


def _parse_job_payload(s: str) -> TranscriptJob | None:
    try:
        data = json.loads(s)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    req = data.get("request_id")
    url = data.get("url")
    uid = data.get("user_id")
    qts = data.get("queued_ts", 0.0)
    if not isinstance(req, str) or not req:
        return None
    if not isinstance(url, str) or not url:
        return None
    if not isinstance(uid, int):
        return None
    try:
        qts_f = float(qts) if qts is not None else 0.0
    except (TypeError, ValueError):
        qts_f = 0.0
    return TranscriptJob(request_id=req, url=url, user_id=uid, queued_ts=qts_f)


class RedisJobQueue(JobQueueProto[TranscriptJob]):
    """Redis protocol-backed queue using BRPOP to avoid polling.

    Configuration via env:
    - `REDIS_URL` (e.g., rediss://default:password@host:port)
    """

    def __init__(
        self,
        *,
        key: str = "transcript:jobs",
        url: str | None = None,
        brpop_timeout_seconds: int | None = None,
    ) -> None:
        self._logger = logging.getLogger(__name__)
        self._key = key
        self._url = (url or os.getenv("REDIS_URL") or "").strip()
        if not self._url:
            raise RuntimeError("Redis URL not configured")
        # Decode responses as str for JSON parsing
        self._client: _RedisClientProto = _redis_from_url(self._url)
        # Blocking pop timeout: 0 = indefinite (recommended). If None provided, default to 0.
        self._brpop_timeout_seconds: int = int(brpop_timeout_seconds or 0)

    async def enqueue(self, job: TranscriptJob) -> None:
        payload = json.dumps(job.__dict__, separators=(",", ":"))
        await self._client.lpush(self._key, payload)

    async def pop(self) -> TranscriptJob | None:
        # Block until a job is available; cancellation stops the worker cleanly
        try:
            res = await self._client.brpop(self._key, timeout=self._brpop_timeout_seconds)
        except asyncio.CancelledError:
            raise
        if not res:
            return None
        _, value = res
        if isinstance(value, str):
            return _parse_job_payload(value)
        return None

    def is_blocking(self) -> bool:
        # BRPOP is a blocking operation regardless of timeout; 0 = indefinite.
        return True
