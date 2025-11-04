# /train Command — Implementation Plan (Digits)

Status: implementation guide (DiscordBot)

## Overview
Add a strict, minimal `/train` command that enqueues a `digits.train.v1` job to the `digits` RQ queue and returns an ephemeral confirmation with `request_id` and `job_id`. The worker (handwriting-ai) performs training and uploads artifacts to the API (manifest v1.1 only).

## Contracts
- Queue: `digits`
- Target: `handwriting_ai.jobs.digits.process_train_job`
- Payload fields: `type`, `request_id`, `user_id`, `model_id`, `epochs`, `batch_size`, `lr`, `seed`, `augment`, `notes`
- Events channel (optional): `digits:events` (`started`, `completed`, `failed`)

## Wiring
1) container.py
- When `REDIS_URL` is present, create `RQDigitsEnqueuer(redis_url=cfg.REDIS_URL, queue_name="digits", job_timeout_s=25200, result_ttl_s=86400, failure_ttl_s=604800, retry_max=2, retry_intervals_s=(60, 300))`.
- Pass it to `DigitsCog` at construction.

2) cogs/digits.py
- Update `DigitsCog.__init__` to accept `enqueuer: DigitsEnqueuer | None = None`.
- Add `/train` command:
  - Defer (ephemeral), generate `request_id` via `BaseCog.new_request_id()`, call `set_request_id(request_id)`.
  - Defaults (no user args): `model_id="mnist_resnet18_v1"`, `epochs=1`, `batch_size=256`, `lr=0.0015`, `seed=42`, `augment=True`, `notes="requested via /train"`.
  - If enqueuer is `None`, reply ephemeral "Training is not configured." and return.
  - Otherwise call `enqueue_train(...)` (pass `request_id` and `user_id` from `interaction.user.id`), capture `job_id`.
  - Reply ephemeral: `Training started (req=<req>, job=<job>).`
  - Optional: rate limit via `RateLimiter`.

## Environment
- DiscordBot: `HANDWRITING_API_URL`, `HANDWRITING_API_KEY` (for `/read`), `REDIS_URL` (for `/train`).
- Worker: `REDIS_URL`, `RQ__QUEUE=digits`, `HANDWRITING_API_URL`, `HANDWRITING_API_KEY`.

## Tests
- Unit: stub enqueuer to verify payload defaults and ephemeral reply contains ids.
- Guard: when enqueuer absent, ephemeral error is returned.

## Notes
- Training modifiers (noise/blur/morph, default-off) live in handwriting-ai `TrainConfig`; `/train` uses defaults only to keep DiscordBot thin and avoid drift.
- API enforces manifest schema_version `v1.1` only.
