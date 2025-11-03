from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:  # narrow sync redis surface for typing

    class _RedisSyncProto(Protocol):  # pragma: no cover - typing only
        def publish(self, channel: str, message: str) -> int: ...

    def _redis_from_url(url: str) -> _RedisSyncProto: ...
else:  # pragma: no cover - runtime import only

    def _redis_from_url(url: str):
        import redis

        return redis.from_url(url, decode_responses=True)


class TranscriptEnqueuer(Protocol):
    def enqueue_transcript(
        self, *, request_id: str, url: str, user_id: int
    ) -> str:  # pragma: no cover - interface
        ...


@dataclass(frozen=True)
class RQTranscriptEnqueuer(TranscriptEnqueuer):
    redis_url: str
    queue_name: str = "transcript"
    job_timeout_s: int = 600
    result_ttl_s: int = 86400
    failure_ttl_s: int = 604800
    retry_max: int = 2
    retry_intervals_s: tuple[int, int] = (60, 300)

    def enqueue_transcript(self, *, request_id: str, url: str, user_id: int) -> str:
        from rq import Queue
        from rq.retry import Retry

        conn = _redis_from_url(self.redis_url)
        q = Queue(self.queue_name, connection=conn)
        retry = Retry(max=self.retry_max, interval=list(self.retry_intervals_s))
        payload = {"request_id": request_id, "url": url, "user_id": user_id}
        job = q.enqueue(
            "src.clubbot.workers.transcript.process_transcript_job",
            payload,
            job_timeout=self.job_timeout_s,
            result_ttl=self.result_ttl_s,
            failure_ttl=self.failure_ttl_s,
            retry=retry,
            description=f"transcript:{request_id}",
        )
        return job.get_id()
