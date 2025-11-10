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

        # RQ stores binary (pickled) payloads; decode_responses must be False
        return redis.from_url(url, decode_responses=False)


class DigitsEnqueuer(Protocol):
    def enqueue_train(
        self,
        *,
        request_id: str,
        user_id: int,
        model_id: str,
        epochs: int,
        batch_size: int,
        lr: float,
        seed: int,
        augment: bool,
        notes: str | None = None,
    ) -> str:  # pragma: no cover - interface
        ...


@dataclass(frozen=True)
class RQDigitsEnqueuer(DigitsEnqueuer):
    redis_url: str
    queue_name: str = "digits"
    job_timeout_s: int = 25200  # 7 hours
    result_ttl_s: int = 86400
    failure_ttl_s: int = 604800
    retry_max: int = 2
    retry_intervals_s: tuple[int, int] = (60, 300)

    def enqueue_train(
        self,
        *,
        request_id: str,
        user_id: int,
        model_id: str,
        epochs: int,
        batch_size: int,
        lr: float,
        seed: int,
        augment: bool,
        notes: str | None = None,
    ) -> str:
        from rq import Queue, Retry

        conn = _redis_from_url(self.redis_url)
        q = Queue(self.queue_name, connection=conn)
        retry = Retry(max=self.retry_max, interval=list(self.retry_intervals_s))
        payload = {
            "type": "digits.train.v1",
            "request_id": request_id,
            "user_id": int(user_id),
            "model_id": str(model_id),
            "epochs": int(epochs),
            "batch_size": int(batch_size),
            "lr": float(lr),
            "seed": int(seed),
            "augment": bool(augment),
            "notes": (str(notes) if isinstance(notes, str) and notes else None),
        }
        job = q.enqueue(
            "handwriting_ai.jobs.digits.process_train_job",
            payload,
            job_timeout=self.job_timeout_s,
            result_ttl=self.result_ttl_s,
            failure_ttl=self.failure_ttl_s,
            retry=retry,
            description=f"digits:{request_id}",
        )
        return job.get_id()
