# Specification and Roadmap

This document summarizes the current implementation in this repository and distinguishes it from future roadmap concepts.

Last updated: 2025-10-30

## Current Implementation (This Repo)

- Commands
  - `/qrcode` — PNG response; validation, rate limits; public/ephemeral toggle
  - `/transcript` — captions via YouTube or STT via `TRANSCRIPT_PROVIDER=stt`
- Background Jobs
  - Typed `JobRunner` with `retry_policy` and `failure_callback` hooks
  - Shared factories: `default_retry_policy_factory`, `failure_notifier_factory`
  - Queue: Redis protocol (BRPOP listener) via `REDIS_URL`
- Metrics
  - SQLite-backed metrics; no Postgres dependency

## Roadmap (Not Implemented Here)

- Members, tasks, events, points/leaderboards domain
- PostgreSQL tables and associated flows
- OAuth/YouTube Data API captions for arbitrary videos (API key only is insufficient)
- Rich UI/embeds for additional commands beyond the LVP

## Background Jobs (Design Guarantees)

- No silent failures: users are DM’d on first user error, or final system failure
- No retries for user-caused errors (via retry policy)
- Consistent DM utilities via `BaseCog.notify_user` / `BaseCog.dm_file`

See also: `docs/Background-Jobs.md`
