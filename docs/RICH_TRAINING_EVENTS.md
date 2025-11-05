# Rich Training Events (v1) — DiscordBot Subscriber & UX

Status: implemented (v1-only)
Audience: DiscordBot maintainers
Principles: strict typing, DRY, non-blocking, clear UX, no legacy fallbacks

## Overview

The bot consumes versioned training events from the handwriting service via Redis Pub/Sub on `digits:events`. The service now emits only v1 events; legacy compact event types are removed. The subscriber decodes v1 events strictly and updates a single DM message per training request.

- Transport: Redis Pub/Sub
- Channel: `digits:events` (configurable in code; default retained)
- Contract: v1-only payloads (see below). No back-compat or fallbacks.
- Behavior: best-effort updates; message edits never block the subscriber loop

## Event Types (v1)

Common fields are included in each payload (enforced by the producer, validated by the bot’s decoder):
- `request_id: string`
- `user_id: number`
- `model_id: string`
- `run_id: string | null` (set after artifacts exist)
- `ts: string` (ISO 8601)

Supported events in the bot:
- `digits.train.started.v1`: `{ total_epochs }`
- `digits.train.epoch.v1`: `{ epoch, total_epochs, train_loss, val_acc, time_s }`
- `digits.train.completed.v1`: `{ val_acc }`
- `digits.train.failed.v1`: `{ error_kind: 'user' | 'system', message }`

The producer may emit additional v1 events (e.g., `batch.v1`, `best.v1`, `artifact.v1`, `upload.v1`, `prune.v1`). The bot ignores unknown event types by design.

## Subscriber Design

- File: `src/clubbot/services/jobs/digits_notifier.py`
- Decoder: `src/clubbot/services/jobs/digits_events.py` exposes `try_decode_event()` for v1 types only
- Flow:
  1. Subscribe to `digits:events`
  2. For each message: decode ? route to a handler ? edit a single DM message for the user
  3. Swallow decoding/handler exceptions to keep the loop healthy; log at debug

## Message UX (v1-only)

- started.v1 ? Create the initial DM with model id and request id
- epoch.v1 ? Edit the message to show current epoch, total epochs, and `val_acc`
- completed.v1 ? Finalize with best `val_acc` and `run_id` (when present)
- failed.v1 ? Finalize with user- or system-facing error text

## Throttled Display (concept)

Batch-level events can be high-frequency. “Throttled display” means we:
- Update the Discord message at most every N milliseconds (e.g., 1000 ms)
- Coalesce intermediate updates in memory and apply the latest state on the next tick
- Always render epoch/completed/failed immediately (not throttled)

Note: The current bot processes epoch/completed/failed v1 events. If we choose to surface batch.v1 later, we will add a small timer-based throttle in the subscriber to avoid chat spam while maintaining responsiveness.

## Strictness & Guarantees

- v1-only decoder; rejects unknown or malformed payloads
- No `Any`, no `type: ignore`, no casts; mypy strict
- Subscriber errors are isolated and never block Redis consumption
- Tests cover decoding branches and notifier behavior

## Tests

- `tests/clubbot/services/test_digits_events_unit.py`: strict decode/encode of v1 events with negative cases
- `tests/clubbot/services/test_digits_notifier_unit.py`: handler routes update DM text for started/epoch/completed/failed

## Deployment Notes

- Ensure the bot has `REDIS_URL` configured (subscriber constructed in `DigitsCog`)
- The service and bot must agree on the channel name (`digits:events`) and v1 contract
