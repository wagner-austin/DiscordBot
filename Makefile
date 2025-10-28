.PHONY: help install install-dev lock run serve test invite env lint lint-fix format typecheck check commands validate-transcript

help:
	@echo "Targets:"
	@echo "  make install   - Install dependencies with Poetry"
	@echo "  make run       - Run the bot locally"
	@echo "  make serve     - Alias for run"
	@echo "  make commands  - Print current global/guild commands"
	@echo "  make test      - Run test suite"
	@echo "  make invite    - Print OAuth2 invite URL"
	@echo "  make env       - Show required env vars"
	@echo "  make validate-transcript URL=<youtube-url>  - Fetch + clean transcript via provider"
	@echo "  make upstash-health  - Probe Upstash REST credentials and pipeline"

install:
	poetry lock
	poetry install

install-dev:
	poetry lock
	poetry install --with dev

run:
	poetry lock
	poetry install
	-poetry run python scripts/invite.py
	-poetry run python scripts/list_commands.py --global --from-env
	poetry run python -m clubbot.main

serve: run

test: install-dev
	poetry run pytest -q

invite:
	poetry run python scripts/invite.py

commands:
	poetry run python scripts/list_commands.py --global --from-env

env:
	@echo "Required: DISCORD_TOKEN"
	@echo "Optional (recommended for dev): DISCORD_GUILD_ID or DISCORD_GUILD_IDS"
	@echo "Optional (for invite URL): DISCORD_APPLICATION_ID, DISCORD_PERMISSIONS"
	@echo "Config file (preferred overrides): clubbot.toml (optional overrides)"
	@echo "  - TRANSCRIPT_PROVIDER = stt|youtube"
	@echo "  - OPENAI_API_KEY (for STT)"
	@echo "  - TRANSCRIPT_MAX_VIDEO_MINUTES or TRANSCRIPT_MAX_VIDEO_SECONDS"
	@echo "  - TRANSCRIPT_MAX_FILE_MB"

validate-transcript: install-dev
	@if [ -z "$(URL)" ]; then echo "Usage: make validate-transcript URL=<youtube-url>"; exit 1; fi
	poetry run python scripts/validate_transcript.py $(URL)

upstash-health: install-dev
	poetry run python scripts/upstash_health.py

lint:
	poetry run ruff check .

lint-fix:
	poetry run ruff check . --fix

format:
	poetry run ruff format .

typecheck:
	poetry run mypy

check: install-dev
	-poetry run ruff check . --fix
	poetry run ruff format .
	poetry run mypy
	poetry run pytest -q

