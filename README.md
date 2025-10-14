# Discord Club Bot LVP

Least-viable product: a modular Python bot that provides a `/qrcode` slash command returning a PNG in an ephemeral response. Built with Poetry and py-cord.

## Features
- `/qrcode url:<https://...> [error_correction] [box_size] [border] [fill_color] [back_color]`
  - Tip: You can omit the scheme. `google.com` or `www.example.org/path` are accepted and normalized to `https://...`.
- Brandable defaults via env vars
- Input validation and friendly errors
  - URL normalization: accepts bare domains and adds `https://` automatically
  - Response includes a clickable hyperlink to the destination URL for confirmation
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
- Create a new project from this repo
- Set Environment Variables:
  - `DISCORD_TOKEN`, `DISCORD_GUILD_ID` or `DISCORD_GUILD_IDS`
  - Optional QR defaults
- Start command: `python -m clubbot.main`

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
