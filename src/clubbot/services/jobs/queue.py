from __future__ import annotations

import asyncio
import json
import logging
import os
import urllib.parse as _url
from dataclasses import dataclass
from typing import Generic, Protocol, TypedDict, TypeVar

import httpx


class JobBase(Protocol):
    request_id: str
    user_id: int


@dataclass(frozen=True)
class TranscriptJob(JobBase):
    request_id: str
    url: str
    user_id: int


T = TypeVar("T", bound=JobBase)


class JobQueueProto(Protocol, Generic[T]):
    async def enqueue(self, job: T) -> None: ...
    async def pop(self) -> T | None: ...


class MemoryJobQueue(Generic[T], JobQueueProto[T]):
    def __init__(self) -> None:
        self._q: asyncio.Queue[T] = asyncio.Queue()

    async def enqueue(self, job: T) -> None:
        await self._q.put(job)

    async def pop(self) -> T | None:
        try:
            return self._q.get_nowait()
        except asyncio.QueueEmpty:
            return None


class UpstashJobQueue(JobQueueProto[TranscriptJob]):
    def __init__(self, *, key: str = "transcript:jobs") -> None:
        self._url = os.getenv("UPSTASH_REDIS_REST_URL", "").strip().rstrip("/")
        self._token = os.getenv("UPSTASH_REDIS_REST_TOKEN", "").strip()
        self._key = key
        self._client = httpx.AsyncClient(timeout=10.0)
        self._logger = logging.getLogger(__name__)

    async def _pipeline(self, commands: list[list[str]]) -> list[object]:
        if not self._url or not self._token:
            raise RuntimeError("Upstash Redis is not configured")
        resp = await self._client.post(
            f"{self._url}/pipeline",
            headers={"Authorization": f"Bearer {self._token}"},
            json={"pipeline": commands},
        )
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:  # enrich with response body for diagnostics
            detail = resp.text
            self._logger.error("Upstash REST  %s: %s", resp.status_code, detail)
            raise httpx.HTTPStatusError(
                f"{e} body={detail}", request=resp.request, response=resp
            ) from e
        data = resp.json()
        return data if isinstance(data, list) else []

    async def enqueue(self, job: TranscriptJob) -> None:
        payload = json.dumps(job.__dict__, separators=(",", ":"))
        enc = _url.quote(payload, safe="")
        r = await self._client.post(
            f"{self._url}/lpush/{self._key}/{enc}",
            headers={"Authorization": f"Bearer {self._token}"},
        )
        r.raise_for_status()

    async def pop(self) -> TranscriptJob | None:
        # Use RPOP for broad REST compatibility
        r = await self._client.get(
            f"{self._url}/rpop/{self._key}",
            headers={"Authorization": f"Bearer {self._token}"},
        )
        r.raise_for_status()
        data = r.json()
        if not isinstance(data, dict):
            return None
        res = data.get("result")
        if res is None:
            return None
        if isinstance(res, str):
            return _parse_job_payload(res)
        return None


def build_queue() -> JobQueueProto[TranscriptJob]:
    mem: MemoryJobQueue[TranscriptJob] = MemoryJobQueue()
    if os.getenv("UPSTASH_REDIS_REST_URL") and os.getenv("UPSTASH_REDIS_REST_TOKEN"):
        primary = UpstashJobQueue()
        return FallbackJobQueue(
            primary=primary,
            secondary=mem,
            logger=logging.getLogger(__name__),
        )
    return mem


class FallbackJobQueue(JobQueueProto[T], Generic[T]):
    def __init__(
        self,
        *,
        primary: JobQueueProto[T],
        secondary: JobQueueProto[T],
        logger: logging.Logger | None = None,
    ) -> None:
        self._primary = primary
        self._secondary = secondary
        self._use_secondary = False
        self._logger = logger or logging.getLogger(__name__)

    async def enqueue(self, job: T) -> None:
        if not self._use_secondary:
            try:
                await self._primary.enqueue(job)
                return
            except (httpx.HTTPError, RuntimeError, OSError) as e:
                self._logger.error("Primary queue failed on enqueue; falling back: %s", e)
                self._use_secondary = True
        await self._secondary.enqueue(job)

    async def pop(self) -> T | None:
        if self._use_secondary:
            return await self._secondary.pop()
        try:
            return await self._primary.pop()
        except (httpx.HTTPError, RuntimeError, OSError) as e:
            self._logger.error("Primary queue failed on pop; falling back: %s", e)
            self._use_secondary = True
            return await self._secondary.pop()


class _JobPayload(TypedDict):
    request_id: str
    url: str
    user_id: int


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
    if not isinstance(req, str) or not req:
        return None
    if not isinstance(url, str) or not url:
        return None
    if not isinstance(uid, int):
        return None
    return TranscriptJob(request_id=req, url=url, user_id=uid)
