"""Tests for edge cases and error handling in digits_notifier."""

from __future__ import annotations

from types import SimpleNamespace

import discord
import pytest
import src.clubbot.services.jobs.digits_notifier as dn


class _FailingUser:
    """Mock user that raises Discord API exceptions."""

    async def send(self, content: str = "", **kw: object) -> object:
        raise discord.Forbidden(
            response=SimpleNamespace(status=403, reason="Forbidden"),
            message="Cannot send DM to user",
        )


class _FailingBot:
    def __init__(self) -> None:
        self.user = _FailingUser()

    async def fetch_user(self, user_id: int) -> _FailingUser:
        _ = user_id
        return self.user


@pytest.mark.asyncio
async def test_notify_handles_discord_forbidden_gracefully() -> None:
    """Test that _notify handles Discord.Forbidden exceptions gracefully."""
    bot = _FailingBot()
    sub = dn.DigitsEventSubscriber(bot, redis_url="redis://fake")

    # Send failed event - should handle exception and not crash
    await sub._handle_event(
        {
            "type": "digits.train.failed.v1",
            "request_id": "r_forbidden",
            "user_id": 999,
            "model_id": "mnist",
            "run_id": None,
            "ts": "2025-01-01T00:00:00Z",
            "error_kind": "system",
            "message": "Test error",
            "queue": "digits",
            "status": "failed",
        }
    )

    # No exception should be raised, just logged


class _HTTPExceptionUser:
    """Mock user that raises HTTP exceptions."""

    async def send(self, content: str = "", **kw: object) -> object:
        raise discord.HTTPException(
            response=SimpleNamespace(status=429, reason="Too Many Requests"),
            message="Rate limited",
        )


class _HTTPExceptionBot:
    def __init__(self) -> None:
        self.user = _HTTPExceptionUser()

    async def fetch_user(self, user_id: int) -> _HTTPExceptionUser:
        _ = user_id
        return self.user


@pytest.mark.asyncio
async def test_notify_handles_http_exception_gracefully() -> None:
    """Test that _notify handles Discord.HTTPException gracefully."""
    bot = _HTTPExceptionBot()
    sub = dn.DigitsEventSubscriber(bot, redis_url="redis://fake")

    # Send started event - should handle exception and not crash
    await sub._handle_event(
        {
            "type": "digits.train.started.v1",
            "request_id": "r_http_error",
            "user_id": 998,
            "model_id": "mnist",
            "run_id": None,
            "ts": "2025-01-01T00:00:00Z",
            "total_epochs": 1,
            "queue": "digits",
        }
    )

    # No exception should be raised, just logged


class _NotFoundUser:
    """Mock user that raises NotFound exceptions."""

    async def send(self, content: str = "", **kw: object) -> object:
        raise discord.NotFound(
            response=SimpleNamespace(status=404, reason="Not Found"),
            message="User not found",
        )


class _NotFoundBot:
    def __init__(self) -> None:
        self.user = _NotFoundUser()

    async def fetch_user(self, user_id: int) -> _NotFoundUser:
        _ = user_id
        return self.user


@pytest.mark.asyncio
async def test_notify_handles_not_found_gracefully() -> None:
    """Test that _notify handles Discord.NotFound exceptions gracefully."""
    bot = _NotFoundBot()
    sub = dn.DigitsEventSubscriber(bot, redis_url="redis://fake")

    # Send completed event - should handle exception and not crash
    await sub._handle_event(
        {
            "type": "digits.train.completed.v1",
            "request_id": "r_not_found",
            "user_id": 997,
            "model_id": "mnist",
            "run_id": "run_123",
            "ts": "2025-01-01T00:10:00Z",
            "val_acc": 0.95,
        }
    )

    # No exception should be raised, just logged
