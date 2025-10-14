FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    POETRY_VERSION=1.8.3 \
    POETRY_VIRTUALENVS_CREATE=false

WORKDIR /app

# Install Poetry
RUN pip install --no-cache-dir "poetry==${POETRY_VERSION}"

# First, install only dependencies to leverage Docker layer caching
COPY pyproject.toml poetry.lock /app/
RUN poetry install --no-interaction --no-ansi --no-root

# Now copy the source and install the project package itself
COPY src /app/src
COPY scripts /app/scripts
RUN poetry install --no-interaction --no-ansi

# Default command runs the bot
CMD ["python", "-m", "clubbot.main"]

