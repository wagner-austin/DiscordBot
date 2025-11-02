# Background Jobs (RQ + Events)

This bot uses durable RQ jobs for STT transcription and handles user notifications via a Redis pub/sub event channel. The captions-only provider (YouTube) executes inline without any queue.

## Current Architecture

- STT provider (durable):
  - Enqueuer: `src/clubbot/services/jobs/rq_enqueuer.py` (`RQTranscriptEnqueuer`)
  - Worker: `src/clubbot/workers/transcript.py:process_transcript_job`
  - Events + result storage: `src/clubbot/services/jobs/events.py` (publish/subscribe + content key)
  - Notifier (in bot process): `src/clubbot/services/jobs/notifier.py` (`TranscriptEventSubscriber`)
- YouTube provider (inline):
  - Runs in the interaction process; no Redis/RQ required.

## How It Works (STT)

1) Bot process enqueues a job via RQ

```py
from src.clubbot.services.jobs.rq_enqueuer import RQTranscriptEnqueuer

enq = RQTranscriptEnqueuer(redis_url=cfg.REDIS_URL)
job_id = enq.enqueue_transcript(request_id=req_id, url=url, user_id=user_id)
```

- The job payload is strictly typed (`TranscriptPayload`: `request_id`, `url`, `user_id`).
- Retry policy, timeouts, and TTLs are set at enqueue-time.

2) Separate RQ worker process executes the job function

```py
# src/clubbot/workers/transcript.py
def process_transcript_job(payload: TranscriptPayload) -> None:
    # Calls TranscriptService.fetch_cleaned(url) off the event loop
    # Publishes a completion/failed event and stores results in Redis
```

- On success: stores the transcript text in Redis using a key built from `TRANSCRIPT_RESULT_KEY_PREFIX` and publishes a `completed` event to `TRANSCRIPT_EVENTS_CHANNEL`.
- On user error: publishes a `failed` event with `error_kind="user"` (no retry).
- On system error: publishes a `failed` event with `error_kind="system"`, then re-raises so RQ retries according to policy.

3) Bot process subscribes to events and DMs users

```py
# src/clubbot/services/jobs/notifier.py
subscriber = TranscriptEventSubscriber(bot, redis_url=cfg.REDIS_URL)
subscriber.start()
```

- On `completed`: fetches the transcript from Redis (by content key) and DMs it as a file.
- On `failed`: DMs a user-facing explanation (user vs system).

## Configuration (STT + RQ)

- `REDIS_URL` (required when `TRANSCRIPT_PROVIDER=stt`) — connection for both RQ and pub/sub.
- `RQ_TRANSCRIPT_JOB_TIMEOUT_SEC` (default `600`) — per-job timeout.
- `RQ_TRANSCRIPT_RESULT_TTL_SEC` (default `86400`) — TTL for stored transcript text.
- `RQ_TRANSCRIPT_FAILURE_TTL_SEC` (default `604800`) — TTL for failed job records.
- `RQ_TRANSCRIPT_RETRY_MAX` (default `2`) and `RQ_TRANSCRIPT_RETRY_INTERVALS_SEC` (default `60,300`) — bounded retries.
- `TRANSCRIPT_EVENTS_CHANNEL` (default `transcript:events`) — Redis pub/sub channel.
- `TRANSCRIPT_RESULT_KEY_PREFIX` (default `transcript:result:`) — Redis key prefix for transcript text.
- `TRANSCRIPT_MAX_ATTACHMENT_MB` (default `25`) — DM attachment size cap.

Worker start (example): `rq worker transcript --with-scheduler`

## Provider Behavior

- `TRANSCRIPT_PROVIDER=youtube` — inline execution; no Redis dependency.
- `TRANSCRIPT_PROVIDER=stt` — RQ-based durable transcription; requires `REDIS_URL`.

## Legacy (BRPOP Queue)

A minimal BRPOP-based queue and runner remain in the codebase for historical and testing purposes:

- Queue and runner: `src/clubbot/services/jobs/queue.py`, `src/clubbot/services/jobs/runner.py`, `src/clubbot/services/jobs/helpers.py`
- Environment: `JOB_QUEUE_BRPOP_TIMEOUT_SECONDS` controls the BRPOP timeout (default `0` = indefinite).

These components are not used for STT. The YouTube provider runs inline; tests may inject `MemoryJobQueue` or use the legacy queue for controlled scenarios. New background-job functionality for STT should use RQ as described above.

## Guarantees

- User-caused errors are not retried and generate a single DM notification.
- System/transient errors are retried with backoff up to the configured limits; users are notified only on final failure.
- No background job silently fails; success and failure states produce events and logs.

