# Background Jobs (Typed, Reusable)

This bot uses a small, typed job runner and queues to perform background work (e.g., transcribing audio) without blocking Discord interactions. The design enforces clear user notifications and strict typing.

## Components

- `JobBase` (Protocol)
  - Required job fields: `request_id: str`, `user_id: int`.
- `JobQueueProto[T: JobBase]`
  - Implementation: `RedisJobQueue` — Redis protocol (BRPOP listener; zero idle polls with indefinite block)
  - `build_queue(brpop_timeout_seconds=...)` constructs a `RedisJobQueue`. Default timeout is `0` (indefinite block).
- `JobRunner[T: JobBase]`
  - Executes jobs with a single handler coroutine.
  - Hooks:
    - `retry_policy(job, exc, attempt) -> bool` — decide if the runner should retry the failure.
    - `failure_callback(job, exc, attempt, will_retry)` — notify users/log values when a failure occurs.
- Helper factories (strict typing, no Any/casts):
  - `default_retry_policy_factory(UserInputError)` — disables retries for user-caused errors.
  - `failure_notifier_factory(notify_fn, service_name)` — DMs users on first user error or final system failure.

## Usage Pattern

1) Define a job type implementing `JobBase` (usually a dataclass):

```py
@dataclass(frozen=True)
class MyJob(JobBase):
    request_id: str
    user_id: int
    payload: str
```

2) Provide a handler (raise `UserInputError` for user-facing problems):

```py
async def handle(job: MyJob) -> None:
    # do work; raise UserInputError("bad input") for validation failures
    ...
```

3) Construct the runner with shared hooks:

```py
queue = build_queue(brpop_timeout_seconds=cfg.JOB_QUEUE_BRPOP_TIMEOUT_SECONDS)
# Requires REDIS_URL; Redis listener. Timeout 0 = indefinite block.
runner = JobRunner[MyJob](
    queue=queue,
    handler=handle,
    failure_callback=failure_notifier_factory(
        notify_fn=self.notify_user,  # BaseCog helper
        service_name="my-service",
    ),
    retry_policy=default_retry_policy_factory(UserInputError),
    retry_attempts=1,
    retry_backoff=1.0,
)
runner.start()
```

4) Enqueue jobs where appropriate:

```py
await queue.enqueue(MyJob(request_id=req_id, user_id=user_id, payload="..."))
```

### Listener Model

- With `RedisJobQueue`, the consumer uses `BRPOP` to block until work arrives. By default the timeout is 0 (indefinite), which eliminates idle polling traffic. Configure `JOB_QUEUE_BRPOP_TIMEOUT_SECONDS` only if your Redis provider requires periodic unblocking to keep connections healthy.

### When the Queue Is Active

- The Transcript feature only starts the background worker (and initializes the Redis queue) when `TRANSCRIPT_PROVIDER=stt`, or when a queue is explicitly injected for tests. In caption-only mode (`youtube`), no Redis connection is created and no background worker runs.

### Configuration

- `REDIS_URL` (e.g., `rediss://default:<password>@<host>:<port>`) — required only when `TRANSCRIPT_PROVIDER=stt`.
- `JOB_QUEUE_BRPOP_TIMEOUT_SECONDS` (default `0`) — BRPOP timeout; `0` means indefinite block. Increase only if your provider drops long-idle connections (e.g., set to `60`).

## Guarantees

- User-caused errors (e.g., invalid inputs) are not retried and are DM’d immediately once.
- System/transient errors retry based on `retry_attempts`; users are DM’d only on final failure.
- No background job silently fails.

## Code References

- `src/clubbot/services/jobs/queue.py`
- `src/clubbot/services/jobs/runner.py`
- `src/clubbot/services/jobs/helpers.py`
