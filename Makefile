.PHONY: help install install-dev lock run serve test invite env lint lint-fix format typecheck check commands

help:
	@echo "Targets:"
	@echo "  make install   - Install dependencies with Poetry"
	@echo "  make run       - Run the bot locally"
	@echo "  make serve     - Alias for run"
	@echo "  make commands  - Print current global/guild commands"
	@echo "  make test      - Run test suite"
	@echo "  make invite    - Print OAuth2 invite URL"
	@echo "  make env       - Show required env vars"

install:
	poetry lock
	poetry install

install-dev:
	poetry lock
	poetry install --with dev

run:
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
