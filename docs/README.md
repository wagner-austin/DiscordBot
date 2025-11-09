# Discord Club Bot LVP

Least-viable product: Modular Python bot that provides a `/qrcode` slash command returning a PNG. Built with Poetry and discord.py (app commands).

## Features
- `/qrcode url:<https://...>`
  - LVP: only `url` is exposed as a parameter. Styling options use env defaults (see below).
  - Friendly URL handling: `google.com`, `www.example.org/path`, IPv4/IPv6, and `localhost` are accepted and normalized to `https://...`.
- Brandable defaults via env vars (ECC, box size, border, colors)
- Input validation and friendly errors
  - Clear messages for invalid scheme/host and overly long URLs
  - Response includes a clickable hyperlink to the destination URL for confirmation
- Public responses by default: the PNG and a clickable link are visible to everyone; validation and rate-limit messages remain ephemeral
  - Visibility: validation messages are always ephemeral; rate-limit messages follow `QR_PUBLIC_RESPONSES` (public by default)
- Modular structure (cogs, services, utils)
- Global-only app commands (no per-guild copies) with DM support enabled

- `/transcript url:<YouTube URL>`
  - Fetches captions when available (default provider = `youtube`).
  - Optional STT provider (`TRANSCRIPT_PROVIDER=stt`) downloads audio and transcribes it.
  - Preflight checks (STT): blocks jobs exceeding configured duration/size before queueing.
  - Background jobs: user is DM’d on success and on first user error or final failure (no silent waits).

## Prerequisites
- Python 3.11+
- Poetry
- A Discord Application with a Bot token
- Developer Portal > Bot > Privileged Gateway Intents: enable 'Message Content Intent'

## Setup
1. Copy `.env.example` to `.env` and fill in values (at least `DISCORD_TOKEN`).
2. Install deps: `poetry install`
3. One-time global sync (first run only): set `COMMANDS_SYNC_ON_START=true` in `.env`, then run `make run`. After you see "Performed global command sync", set it back to `false`.
4. Invite the bot to a server:
   - Developer Portal > OAuth2 > URL Generator
   - Scopes: `bot`, `applications.commands`
   - Permissions: View Channels, Send Messages, Attach Files, Embed Links, Read Message History, Use Application Commands
   - Or run `poetry run python scripts/invite.py`
5. Use `/qrcode` in a server or a DM. Global command propagation can take up to ~1 hour on first registration.

## Deployment

## Developer Index

- Add a new slash command
  - Create a cog in `src/clubbot/cogs/<name>.py`.
  - Use `@app_commands.command` and set `@app_commands.allowed_contexts`/`allowed_installs` as needed.
  - Inherit from `BaseCog` and use `handle_user_error` and `handle_exception`.
  - Validate inputs early and consider `RateLimiter` for per-user limits.
  - Provide an `async def setup(bot)` to allow bot to load the cog.

- Add a new queued service
  - Follow `docs/Background-Jobs.md`.
  - Define a dataclass job implementing `JobBase` (fields: `request_id`, `user_id`).
  - Build a `JobRunner` with `failure_notifier_factory(self.notify_user, service_name=...)` and `default_retry_policy_factory(UserInputError)`.
  - Start the runner in the cogâ€™s `__init__` and enqueue jobs when appropriate.

- Sync/verify commands
  - Set `COMMANDS_SYNC_ON_START=true` and run `make run`; after the sync message appears, set back to `false`.
  - Inspect via `scripts/list_commands.py`.

- Run checks and tests
  - `make check` (ruff, format, mypy, pytest)
  - `make test` for tests only
- Build via Dockerfile (included) or run with a process manager.
- Environment Variables:
  - `DISCORD_TOKEN` (required)
  - Optional QR defaults (see Environment below)
  - `LOG_LEVEL` (e.g., `INFO` or `DEBUG`)
  - `COMMANDS_SYNC_GLOBAL=true` and `COMMANDS_SYNC_ON_START=true` for the first boot after changing commands; then set `COMMANDS_SYNC_ON_START=false`.
  - `BOT_INSTANCE_ID` (optional): overrides the per-process instance id used in logs

## Project Layout
```
src/clubbot/
  main.py               # Bot entry
  config.py             # Env + defaults
  logging.py            # Logging config
  cogs/base.py          # Shared BaseCog (request-scoped logging)
  cogs/qr.py            # /qrcode slash command
  cogs/transcript.py    # /transcript slash command (captions or STT)
  cogs/example.py       # Example cog template (not auto-loaded)
  container.py          # Service container (DI composition)
  services/qr_service.py# QR generation (qrcode + Pillow)
  services/qr_logic.py  # Resolve options & defaults
  services/jobs/queue.py# Legacy BRPOP queue (kept for tests; STT uses RQ)
  services/jobs/runner.py# Generic job runner with retry/failure hooks
  services/jobs/helpers.py# Failure notifier and retry-policy factories (typed)
  services/jobs/rq_enqueuer.py# RQ enqueue adapter (STT)
  services/jobs/notifier.py# Redis pub/sub event subscriber (DM results)
  workers/transcript.py# RQ worker entrypoint
  services/transcript/   # Transcript providers (YouTube captions, STT)
  utils/validators.py   # Input validation
  utils/errors.py       # Error types
  utils/rate_limiter.py # Simple per-user limiter
  utils/correlation.py  # Add request ID header utility
```

## Notes
- This LVP does not include a persistent database; Redis (protocol) is required for background jobs when `TRANSCRIPT_PROVIDER=stt` (set `REDIS_URL`).
- Global-only commands: we sync globally via `bot.tree.sync()` and allow DMs (no per-guild copies by default).
- Propagation: initial global registration may take up to ~1 hour; subsequent edits are often faster.

## Metrics
- Backend: SQLite (default `data/metrics.sqlite`)
- Logs both successes and failures (validation, rate-limit, internal errors)
- Stats command: `/qrstats` (Officers role only). Implemented in `src/clubbot/cogs/qr_stats.py` but not loaded by default — wire `QRStatsCog` in the container to enable it.
- Environment:
  - `METRICS_ENABLED` (default `true`)
  - `METRICS_SQLITE_PATH` (default `data/metrics.sqlite`)
  - `METRICS_REDACT_QUERY` (default `true`) â€” removes query string from stored normalized URLs
  - `QR_STATS_OFFICER_ROLE` (default `officers`)
  - `QR_STATS_DEFAULT_WINDOW` (default `7d`)
  - `QR_STATS_ADMIN_USER_IDS` (comma/space separated user IDs; allowed to use `/qrstats` in DMs)
  - `COMMANDS_SYNC_GLOBAL` (default `false`; when `true` and `COMMANDS_SYNC_ON_START=true`, performs a one-time global sync on boot; propagation may take up to ~1 hour)

## Environment
- Required
  - `DISCORD_TOKEN`
- Optional
  - `LOG_LEVEL`
  - `DISCORD_GUILD_ID` or `DISCORD_GUILD_IDS` (no per-guild copies are created by default; globals cover all guilds)
  - `BOT_INSTANCE_ID` to set a stable id across restarts/containers (otherwise auto-derived)
- QR defaults (brand/styling)
  - `QR_DEFAULT_ERROR_CORRECTION` (L, M, Q, H - default M)
  - `QR_DEFAULT_BOX_SIZE` (default 10)
  - `QR_DEFAULT_BORDER` (default 1)
  - `QR_DEFAULT_FILL_COLOR` (default `#000000`)
  - `QR_DEFAULT_BACK_COLOR` (default `#FFFFFF`)
- Rate limiting (per-user)
  - `QRCODE_RATE_LIMIT` (default 1)
  - `QRCODE_RATE_WINDOW_SECONDS` (default 1)
  - `QR_PUBLIC_RESPONSES` (default `true`) - set to `false` to make success responses ephemeral

- Queues
  - RQ / Events (STT)
    - `REDIS_URL` - Redis connection (required when `TRANSCRIPT_PROVIDER=stt`)
    - `RQ_TRANSCRIPT_JOB_TIMEOUT_SEC` (default `600`) - per-job timeout
    - `RQ_TRANSCRIPT_RESULT_TTL_SEC` (default `86400`) - TTL for stored transcript text
    - `RQ_TRANSCRIPT_FAILURE_TTL_SEC` (default `604800`) - TTL for failed job records
    - `RQ_TRANSCRIPT_RETRY_MAX` (default `2`) and `RQ_TRANSCRIPT_RETRY_INTERVALS_SEC` (default `60,300`) - bounded retries
    - `TRANSCRIPT_EVENTS_CHANNEL` (default `transcript:events`) - Redis pub/sub channel for completion/failure
    - `TRANSCRIPT_RESULT_KEY_PREFIX` (default `transcript:result:`) - Redis key prefix for transcript text
    - `TRANSCRIPT_MAX_ATTACHMENT_MB` (default `25`) - DM attachment size cap
  - Legacy (BRPOP)
    - `JOB_QUEUE_BRPOP_TIMEOUT_SECONDS` - BRPOP timeout, default `0` (indefinite block). Only relevant for legacy queue/tests.

- Transcript
  - `TRANSCRIPT_PROVIDER` (default `youtube`; set `stt` to enable speech-to-text)
  - `OPENAI_API_KEY` (required if `TRANSCRIPT_PROVIDER=stt`)
  - `TRANSCRIPT_PREFERRED_LANGS` (default `en,en-US,en-GB`)
  - `TRANSCRIPT_MAX_VIDEO_SECONDS` (default `5400`) - max duration for STT
  - `TRANSCRIPT_MAX_FILE_MB` (default `25`) - max audio size for STT
  - `TRANSCRIPT_PUBLIC_RESPONSES` (default `false`) - transcript attachments can be ephemeral or public
  - `TRANSCRIPT_STT_API_TIMEOUT_SECONDS` (default `900`) - Whisper API timeout
  - `TRANSCRIPT_STT_API_MAX_RETRIES` (default `2`) - Whisper API retries
  - `TRANSCRIPT_STT_RTF` (default `0.5`) - seconds of processing per audio second (ETA)
  - `TRANSCRIPT_DL_MIB_PER_SEC` (default `4.0`) - download speed for ETA (MiB/s)
  - `TRANSCRIPT_COOKIES_TEXT` - optional Cookie header for YouTube (STT)
  - `TRANSCRIPT_COOKIES_PATH` - optional cookies.txt path for YouTube (STT)
  - Chunking (STT; requires `ffmpeg`/`ffprobe` on PATH):
    - `TRANSCRIPT_ENABLE_CHUNKING` (default `true`)
    - `TRANSCRIPT_CHUNK_THRESHOLD_MB` (default `20.0`)
    - `TRANSCRIPT_TARGET_CHUNK_MB` (default `20.0`)
    - `TRANSCRIPT_MAX_CHUNK_DURATION_SECONDS` (default `600.0`)
    - `TRANSCRIPT_MAX_CONCURRENT_CHUNKS` (default `3`)
    - `TRANSCRIPT_SILENCE_THRESHOLD_DB` (default `-40.0`)
    - `TRANSCRIPT_SILENCE_DURATION_SECONDS` (default `0.5`)

Behavior
- Validation happens before rate limiting so users see clear input errors rather than generic cooldown messages.
- The command defers immediately (ACK first) to avoid Discord's 3s timeout; work runs after the ACK.

## Linting & Formatting
- Lint: `make lint` (ruff check)
- Auto-fix: `make lint-fix`
- Format: `make format`
- Type check: `make typecheck` (strict mypy on src/)
- Check: `make check` (ruff --fix, format, mypy, then pytest)

## Building New Cogs
- Inherit from `clubbot.cogs.base.BaseCog` for consistent logging and errors.
- In app command handlers, call `interaction.response.defer(...)` first; then set up request-scoped logging via `new_request_id()` and `request_logger()`.
- For user validation errors, raise/catch `UserInputError` and use `await self.handle_user_error(interaction, log, message)`.
- For unexpected exceptions, use `await self.handle_exception(interaction, log, exc)`.

### Background Jobs (RQ + Events)
- STT provider uses RQ for durable jobs; YouTube provider runs inline.
- Enqueue STT jobs via `services/jobs/rq_enqueuer.py` (returns `job_id`).
- A separate RQ worker executes `workers/transcript.py:process_transcript_job` and publishes events.
- The bot subscribes via `services/jobs/notifier.py` and DMs users on completion/failure.
- Legacy BRPOP queue/runner remain for tests; new background work for STT should use RQ.

### Background Jobs (Legacy BRPOP)
- Define a job dataclass implementing `JobBase` (fields: `request_id: str`, `user_id: int`).
- Use `JobRunner` with typed hooks:
  - `failure_callback(job, exc, attempt, will_retry)` - see `services/jobs/helpers.py` to DM users on failures.
  - `retry_policy(job, exc, attempt) -> bool` â€” use `default_retry_policy_factory` to skip retries for user errors.
- Queues: `RedisJobQueue` (listener) via `build_queue(brpop_timeout_seconds=cfg.JOB_QUEUE_BRPOP_TIMEOUT_SECONDS)`.
- Base DM helpers: `BaseCog.notify_user(...)` and `BaseCog.dm_file(...)` for consistent user messaging.

Correlation header for outbound HTTP:
- Use `utils.correlation.add_correlation_header(headers, req_id)` to include `X-Request-ID`.

## QR Error Correction Levels
- `L` (Low): ~7% of codewords can be restored. Smallest QR code, most data-efficient; least robust.
- `M` (Medium): ~15% restored. Good default for most cases.
- `Q` (Quartile): ~25% restored. More robust to damage/overlays; larger code.
- `H` (High): ~30% restored. Most robust (e.g., logos/occlusion), largest code.

Note: Default border (quiet zone) is set to 2 modules for compact codes. The QR spec recommends 4 for maximum scanner compatibility; increase via `QR_DEFAULT_BORDER` if needed.




