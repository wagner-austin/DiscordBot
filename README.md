# Discord Club Bot LVP

Least-viable product: a modular Python bot that provides a `/qrcode` slash command returning a PNG in an ephemeral response. Built with Poetry and py-cord.

## Features
- `/qrcode url:<https://...>`
  - LVP: only `url` is exposed as a parameter. Styling options use env defaults (see below).
  - Friendly URL handling: `google.com`, `www.example.org/path`, IPv4/IPv6, and `localhost` are accepted and normalized to `https://...`.
- Brandable defaults via env vars (ECC, box size, border, colors)
- Input validation and friendly errors
  - Clear messages for invalid scheme/host and overly long URLs
  - Response includes a clickable hyperlink to the destination URL for confirmation
- Public responses by default: the PNG and a clickable link to the destination URL are visible to everyone; validation and rate-limit messages remain ephemeral
- Modular structure (cogs, services, utils)

## Prerequisites
- Python 3.11+
- Poetry
- A Discord Application with a Bot token

## Setup
1. Copy `.env.example` to `.env` and fill in values (at least `DISCORD_TOKEN`, and for fast testing `DISCORD_GUILD_ID` or `DISCORD_GUILD_IDS`).
2. Install deps: `poetry install`
3. Run locally: `poetry run python -m clubbot.main`
4. Invite the bot:
   - Developer Portal → OAuth2 → URL Generator
   - Scopes: `bot`, `applications.commands`
   - Permissions: View Channels, Send Messages, Attach Files, Embed Links, Read Message History, Use Application Commands
   - Use the generated URL to add the bot to your server
5. Test `/qrcode` in your server.

## Deployment (Railway)
- Create a new project from this repo.
- In the service settings, set Deployment Method to Dockerfile (this repo includes a Dockerfile).
- Environment Variables (Project → Variables):
  - `DISCORD_TOKEN`, `DISCORD_GUILD_ID` or `DISCORD_GUILD_IDS`
  - Optional QR defaults (see Environment below)
  - Optional `LOG_LEVEL` (e.g., `INFO` or `DEBUG`)
  - Optional `COMMANDS_SYNC_GLOBAL` (`true`/`false`)
- No Start Command needed; Docker CMD runs `python -m clubbot.main` inside the Poetry environment.
- Enable auto‑deploy on push.

## Project Layout
```
src/clubbot/
  main.py               # Bot entry
  config.py             # Env + defaults
  logging.py            # Logging config
  cogs/base.py          # Shared BaseCog (request-scoped logging)
  cogs/qr.py            # /qrcode slash command
  cogs/example.py       # Example cog template (not auto-loaded)
  container.py          # Service container (DI composition)
  services/qr_service.py# QR generation (qrcode + Pillow)
  services/qr_logic.py  # Resolve options & defaults
  utils/validators.py   # Input validation
  utils/errors.py       # Error types
  utils/rate_limiter.py # Simple per-user limiter
  utils/correlation.py  # Add request ID header utility
```

## Notes
- This LVP does not include database or Redis. Those are planned for tasks, points, and leaderboards.
- Commands are registered to the guild in `DISCORD_GUILD_ID` for fast iteration. Remove guild scoping to promote to global commands later.
- During verification, commands are synced only to target guilds (`DISCORD_GUILD_ID`/`DISCORD_GUILD_IDS`). There is no global fallback. Add the bot to the target guild(s) to see commands.

## Metrics
- Backend: SQLite (default `data/metrics.sqlite`)
- Logs both successes and failures (validation, rate-limit, internal errors)
- Stats command: `/qrstats` (Officers role only). No parameters — uses defaults.
- Default window comes from `QR_STATS_DEFAULT_WINDOW` and shows top 10 links.
- Environment:
  - `METRICS_ENABLED` (default `true`)
  - `METRICS_SQLITE_PATH` (default `data/metrics.sqlite`)
  - `METRICS_REDACT_QUERY` (default `true`) — removes query string from stored normalized URLs
  - `QR_STATS_OFFICER_ROLE` (default `officers`)
  - `QR_STATS_DEFAULT_WINDOW` (default `7d`)
  - `QR_STATS_ADMIN_USER_IDS` (comma/space separated user IDs; allowed to use `/qrstats` in DMs)
  - `COMMANDS_SYNC_GLOBAL` (default `false`; when `true` also syncs commands globally so they are available in DMs — propagation may take up to 1 hour)

## Environment
- Required
  - `DISCORD_TOKEN`
- Recommended (fast iteration)
  - `DISCORD_GUILD_ID` or `DISCORD_GUILD_IDS`
- QR defaults (brand/styling)
  - `QR_DEFAULT_ERROR_CORRECTION` (L, M, Q, H — default M)
  - `QR_DEFAULT_BOX_SIZE` (default 10)
  - `QR_DEFAULT_BORDER` (default 1)
  - `QR_DEFAULT_FILL_COLOR` (default `#000000`)
  - `QR_DEFAULT_BACK_COLOR` (default `#FFFFFF`)
- Rate limiting (per-user)
  - `QRCODE_RATE_LIMIT` (default 1)
  - `QRCODE_RATE_WINDOW_SECONDS` (default 1)
  - `QR_PUBLIC_RESPONSES` (default true). When true, responses are public (ephemeral=false). When false, responses are ephemeral (visible only to the requester).
  - `QR_PUBLIC_RESPONSES` (default `true`) — set to `false` to make success responses ephemeral

Behavior
- Validation happens before rate limiting so users always see clear input errors rather than generic cooldown messages.
- After validation and passing the rate limit, the command calls `defer(ephemeral=True)` to guarantee a quick acknowledgement during QR generation.

## Linting & Formatting
- Lint: `make lint` (ruff check)
- Auto-fix: `make lint-fix`
- Format: `make format`
- Type check: `make typecheck` (strict mypy on src/)
 - Check: `make check` (ruff --fix, format, mypy, then pytest)

## Building New Cogs
- Inherit from `clubbot.cogs.base.BaseCog` for consistent logging and errors.
- At the start of each command handler:
  - `req_id = self.new_request_id()`
  - `set_request_id(req_id)` to propagate the id to all logs
  - `log = self.request_logger(req_id)` and use `log.info/debug/...`
- For user validation errors, raise or catch `UserInputError` and use `await self.handle_user_error(ctx, log, message)`.
- For unexpected exceptions, use `await self.handle_exception(ctx, log, exc)`.

Correlation header for outbound HTTP:
- Use `utils.correlation.add_correlation_header(headers, req_id)` to include `X-Request-ID`.

## QR Error Correction Levels
- `L` (Low): ~7% of codewords can be restored. Smallest QR code, most data-efficient; least robust.
- `M` (Medium): ~15% restored. Good default for most cases.
- `Q` (Quartile): ~25% restored. More robust to damage/overlays; larger code.
- `H` (High): ~30% restored. Most robust (e.g., logos/occlusion), largest code.

Note: Default border (quiet zone) is set to 2 modules for compact codes. The QR spec recommends 4 for maximum scanner compatibility; increase via `QR_DEFAULT_BORDER` if needed.
