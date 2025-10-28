FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    POETRY_VERSION=1.8.3 \
    POETRY_VIRTUALENVS_CREATE=false

WORKDIR /app

# System deps (ffmpeg for audio chunking)
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN pip install --no-cache-dir "poetry==${POETRY_VERSION}"

# First, install only dependencies to leverage Docker layer caching
COPY pyproject.toml poetry.lock /app/
# Ensure lock file matches pyproject (handles small, safe edits)
RUN poetry lock --no-interaction --no-ansi --no-update || true \
 && poetry install --no-interaction --no-ansi --no-root

# Now copy the source and install the project package itself
COPY src /app/src
COPY scripts /app/scripts
COPY README.md /app/README.md
RUN poetry install --no-interaction --no-ansi

# Container health check (requires envs and ffmpeg when chunking/STT)
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python scripts/healthcheck.py || exit 1

# Default command runs the bot (importing directly from src/)
CMD ["python", "-m", "src.clubbot.main"]
