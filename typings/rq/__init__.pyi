from __future__ import annotations

from typing import Protocol

from .job import Job

class Retry:
    def __init__(self, max: int, interval: list[int]) -> None: ...

class _RedisConnection(Protocol): ...

class Queue:
    def __init__(self, name: str, connection: _RedisConnection) -> None: ...
    def enqueue(
        self,
        f: str,
        payload: dict[str, object],
        *,
        job_timeout: int,
        result_ttl: int,
        failure_ttl: int,
        retry: Retry,
        description: str,
    ) -> Job: ...
