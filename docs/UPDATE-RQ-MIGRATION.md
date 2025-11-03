# RQ Migration - Durable Background Jobs (Transcription)

Last updated: 2025-11-01
Status: Complete
Audience: Maintainers of DiscordBot
Scope: Replace LPUSH/BRPOP queue for STT transcription with durable RQ jobs (Redis-backed) for the STT provider only. The captions provider (YouTube) continues to run inline.

## Completion Note
The migration is complete and active in production paths:
- STT provider uses RQ for durable jobs with retries/timeouts.
- YouTube provider runs inline without Redis.
- Main docs have been updated: see `docs/Background-Jobs.md` and the Queues section in `docs/README.md`.

## Goals
- Reliability: no job loss if worker crashes mid-run; bounded retries with backoff; explicit timeouts.
- Maintain UX: keep slash command usage minimal (defer + enqueue + DM updates). No extra user commands.
- Strict typing: no `Any`, no `typing.cast`; use Protocols/typed wrappers for `rq` and Redis.
- Low tech debt: isolate RQ details behind small, typed adapters; preserve existing clean patterns.

## Non-Goals
- Introducing Celery or a full observability stack.
- Changing the existing transcript user workflow.

## Current State (Summary)
- Queue: `RedisJobQueue` (BRPOP) in `src/clubbot/services/jobs/queue.py`
  - Pros: simple, minimal deps. Cons: no ACK; job can be lost if worker dies after pop.
- Runner: `JobRunner` (async tasks) in `src/clubbot/services/jobs/runner.py` drives handler coroutine(s).
- Usage: `TranscriptCog` builds a queue and runner for provider `stt`, enqueues `TranscriptJob` with `queued_ts`, and handler DMs results.
- Typing: strict across modules; no casts; clear error boundaries and failure notifier.

## Rationale for RQ
- Built-in ACK and retries; durable job persistence; job status (`queued`, `started`, `failed`, `finished`).
- Simple worker lifecycle (`rq worker transcript --with-scheduler`).
- Metadata storage via `job.meta`; easy for status endpoints or DM updates.

## Design

### 1) Introduce a typed enqueue adapter (no runtime worker loop in the bot)
- New module: `src/clubbot/services/jobs/rq_enqueuer.py`
- Define a Protocol and an RQ implementation:

```
from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol

class TranscriptEnqueuer(Protocol):
    def enqueue_transcript(self, *, request_id: str, url: str, user_id: int) -> str: ...  # returns job_id

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
        from rq import Queue, Retry
        from rq.job import Job  # add local stubs if needed
        import redis

        conn: redis.Redis[str] = redis.from_url(self.redis_url, decode_responses=True)
        q = Queue(self.queue_name, connection=conn)
        retry = Retry(max=self.retry_max, interval=list(self.retry_intervals_s))
        job: Job = q.enqueue(
            "clubbot.workers.transcript.process_transcript_job",  # fully-qualified
            {
                "request_id": request_id,
                "url": url,
                "user_id": user_id,
            },
            job_timeout=self.job_timeout_s,
            result_ttl=self.result_ttl_s,
            failure_ttl=self.failure_ttl_s,
            retry=retry,
            description=f"transcript:{request_id}",
        )
        return job.get_id()
```

- Notes on typing:
  - Avoid `Any` by using Protocols and dataclasses.
  - If `rq` stubs are insufficient, add minimal `.pyi` stubs under `typings/` for the used surface (Queue, Job, Retry) and enable `mypy_path = ["typings"]` (already present).

### 2) Add worker entrypoint that runs in a separate process/container
- New module: `src/clubbot/workers/transcript.py`

```
from __future__ import annotations
import logging
from typing import TypedDict

from ..services.transcript.app import TranscriptService
from ..config import load_config
from ..logging import set_request_id

class TranscriptPayload(TypedDict):
    request_id: str
    url: str
    user_id: int

# RQ worker will import this function by name

def process_transcript_job(payload: TranscriptPayload) -> None:
    cfg = load_config()
    svc = TranscriptService(cfg)
    req = payload["request_id"]
    url = payload["url"]
    user_id = payload["user_id"]
    set_request_id(req)

    # Fetch + clean in thread to keep CPU-bound work off event loop
    import asyncio
    res = asyncio.run(asyncio.to_thread(svc.fetch_cleaned, url))

    # Publish completion event (see Notifier & Events section)
    logging.getLogger(__name__).info("Transcript done req=%s vid=%s", req, res.video_id)
```

- Worker command: `rq worker transcript --with-scheduler` (use same `REDIS_URL`).
- Notification strategy: keep DMs in the bot process by publishing progress/events to Redis Pub/Sub (e.g., `transcript:events`), or establish a small DM helper the worker can call (requires minimal bot token use in worker). Prefer Pub/Sub to keep one tokened process.

### 2a) Notifier & Events (bot-subscribed Pub/Sub)
- Event channel: `transcript:events`
- Result key prefix: `transcript:result:` with configurable TTL.
- Event shapes (JSON; enforce via TypedDicts):

```
from typing import Literal, TypedDict

class TranscriptCompletedEvent(TypedDict):
    type: Literal["completed"]
    request_id: str
    user_id: int
    url: str
    video_id: str
    content_key: str  # Redis key where transcript text is stored

class TranscriptFailedEvent(TypedDict):
    type: Literal["failed"]
    request_id: str
    user_id: int
    error_kind: Literal["user", "system"]
    message: str
```

- Worker behavior:
  - On success: store transcript text at `content_key` with TTL; publish `completed` event.
  - On failure: classify `user|system`; publish `failed` event (no retry for `user`).
- Bot subscriber:
  - Consumes events and DMs users using existing helpers (attachment size checks retained).
  - Cleans up by deleting content or letting TTL expire.

### 3) Wire the enqueuer and subscriber in TranscriptCog (STT only)
- Replace BRPOP queue/runner construction with RQ enqueuer when `TRANSCRIPT_PROVIDER=stt`.
- Start a typed Redis Pub/Sub subscriber service that listens on `transcript:events` and DMs users.
- On slash command, after preflight, call `enqueuer.enqueue_transcript(...)` and return immediate ephemeral confirmation with the `request_id`.
- Remove `JobRunner` usage for STT path (retain it for purely local, non-critical jobs if needed). Keep MemoryJobQueue for unit tests.

### 4) Configuration (Pydantic Settings)
- New envs (documented in README and `.env.example`):
  - `REDIS_URL` — required for RQ.
  - `RQ_TRANSCRIPT_JOB_TIMEOUT_SEC` (default 600)
  - `RQ_TRANSCRIPT_RESULT_TTL_SEC` (default 86400)
  - `RQ_TRANSCRIPT_FAILURE_TTL_SEC` (default 604800)
  - `RQ_TRANSCRIPT_RETRY_MAX` (default 2)
  - `RQ_TRANSCRIPT_RETRY_INTERVALS_SEC` (default `60,300`)
  - `TRANSCRIPT_EVENTS_CHANNEL` (default `transcript:events`)
  - `TRANSCRIPT_RESULT_KEY_PREFIX` (default `transcript:result:`)
- Keep existing `TRANSCRIPT_*` limits and rate limiting.

### 5) Logging, Errors, and Progress
- Use existing logging context (request_id and instance_id) in both producer and worker.
- Failure classification:
  - User errors (e.g., invalid URL, transcripts disabled) should fail fast in the bot preflight and not be enqueued.
  - Transient/network errors retried by RQ according to policy; final failure produces a DM via the notifier.
- Optional: write `job.meta["progress"]` and publish small progress events; the bot polls `job.get_status()` or consumes Pub/Sub to DM updates if desired.
- All events should include `request_id` for traceability.

### 6) Testing Plan
- Unit tests:
  - Enqueue adapter: assert correct payload, queue name, timeout, TTLs, retry config.
  - Worker function: run with a fake payload and stubbed TranscriptService; verify result key stored and completed event published; failed event for user/system errors (user errors not retried).
  - Notifier/subscriber: feed completed/failed events; verify DM behavior and attachment size checks; ensure content retrieval by key.
  - Event parsing: invalid payloads are rejected without raising; log classification.
- Integration tests:
  - Spin up Redis (or use a fake layer); enqueue via adapter; run a worker and a subscriber; assert end-to-end DM with stable `request_id`.
- Typing:
  - mypy strict passes; no `Any` or casts. Add stubs if needed under `typings/`.

### 7) Migration Steps
1) Add `rq` to Poetry dependencies; add minimal type stubs if necessary.
2) Implement `RQTranscriptEnqueuer` and worker function.
3) Implement typed `events` module (event shapes, channel/key constants) and a subscriber service in the bot that DMs users.
4) Wire `TranscriptCog` to use the enqueuer for `stt` provider and start the subscriber; remove BRPOP runner for this path (retain MemoryJobQueue for unit tests).
5) Update `.env.example` and README; add Makefile targets and docker-compose `worker` service.
6) Add tests; verify end-to-end with a small video and ensure `make check` passes.

### 8) Rollback Plan
- Keep existing `MemoryJobQueue` for tests and `BRPOP` components under a feature flag.
- If RQ causes issues, fallback to BRPOPLPUSH + reaper (visibility timeout ˜ 10 min) for STT until issues are resolved.

### 9) Operational Commands
- Local worker: `rq worker transcript --with-scheduler`
- Makefile: add `make worker` to run the worker with current env.
- docker-compose: add a `worker` service using the same `REDIS_URL` and image as the bot.

### 10) Modules & Typing Surfaces
- `src/clubbot/services/jobs/rq_enqueuer.py` — `TranscriptEnqueuer` Protocol and `RQTranscriptEnqueuer` impl.
- `src/clubbot/workers/transcript.py` — `process_transcript_job(payload)` worker function.
- `src/clubbot/services/jobs/events.py` — TypedDicts for events, channel/key constants.
- `src/clubbot/services/jobs/notifier.py` — Subscriber service that consumes events and DMs users.
- `typings/rq/*.pyi` — minimal stubs for `rq.Queue`, `rq.job.Job`, `rq.Retry` if needed to keep mypy strict with no Any/casts.

## Acceptance Criteria
- A 90–180s transcription completes reliably even if the worker restarts mid-run (job is retried/requeued).
- Slash command flow unchanged for users (defer + acknowledgment + DM on completion/failure).
- Strict typing across new modules; no `Any` or `cast` added.
- Lint/type/tests pass via `make check`.

## Notes
- If we later add a status surface: `/status <request_id>` can query `rq.Job` and/or a lightweight Redis manifest keyed by request.
- For reproducible logging across processes, keep the request_id stable and attach instance_id per process (already implemented).
- Consider an optional feature flag `TRANSCRIPT_QUEUE_IMPL=rq|brpop` to allow staged rollout; default to `rq` for `stt`.

