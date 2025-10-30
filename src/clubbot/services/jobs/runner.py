from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from typing import Generic, TypeVar

from .queue import JobBase, JobQueueProto

T = TypeVar("T", bound=JobBase)


class JobRunner(Generic[T]):
    def __init__(
        self,
        queue: JobQueueProto[T],
        handler: Callable[[T], Awaitable[None]],
        *,
        max_concurrency: int = 1,
        retry_attempts: int = 1,
        retry_backoff: float = 1.0,
        idle_sleep: float = 1.0,
        logger: logging.Logger | None = None,
        failure_callback: Callable[[JobBase, Exception, int, bool], Awaitable[None] | None]
        | None = None,
        retry_policy: Callable[[JobBase, Exception, int], bool] | None = None,
    ) -> None:
        self._queue = queue
        self._handler = handler
        self._max_concurrency = max(1, max_concurrency)
        self._retry_attempts = max(0, retry_attempts)
        self._retry_backoff = max(0.0, retry_backoff)
        self._idle_sleep = max(0.1, idle_sleep)
        self._logger = logger or logging.getLogger(__name__)
        self._tasks: list[asyncio.Task[None]] = []
        self._stopping = False
        self._on_failure = failure_callback
        self._retry_policy = retry_policy

    def start(self) -> None:
        if self._tasks:
            return
        for _ in range(self._max_concurrency):
            self._tasks.append(asyncio.create_task(self._worker()))

    async def stop(self) -> None:
        self._stopping = True
        for t in self._tasks:
            t.cancel()
        for t in self._tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await t
        self._tasks.clear()

    async def _worker(self) -> None:  # pragma: no cover - exercised indirectly
        while not self._stopping:
            try:
                job = await self._queue.pop()
                if job is None:
                    await asyncio.sleep(self._idle_sleep)
                    continue
                await self._handle(job)
            except asyncio.CancelledError:
                raise
            except Exception as e:  # worker resilience
                self._logger.exception("Job worker error: %s", e)
                await asyncio.sleep(self._idle_sleep)

    async def _handle(self, job: T) -> None:
        attempt = 0
        delay = self._retry_backoff
        while True:
            try:
                await self._handler(job)
                return
            except Exception as e:
                attempt += 1
                self._logger.exception("Job handler error (attempt %s): %s", attempt, e)
                # Compute retry intention considering attempts and optional policy
                will_retry = attempt <= self._retry_attempts
                if self._retry_policy is not None:
                    try:
                        policy_allows = self._retry_policy(job, e, attempt)
                    except Exception as policy_exc:
                        self._logger.debug("Retry policy raised: %s", policy_exc)
                        policy_allows = True
                    will_retry = will_retry and bool(policy_allows)

                # Invoke optional failure callback with retry hint
                if self._on_failure is not None:
                    try:
                        result = self._on_failure(job, e, attempt, will_retry)
                        if result is not None:
                            await result
                    except Exception as cb_exc:
                        self._logger.debug("Failure callback raised: %s", cb_exc)
                if not will_retry:
                    return
                await asyncio.sleep(delay)
                delay = max(delay * 2.0, self._retry_backoff)
