from __future__ import annotations

import types

import discord
import pytest
from discord.ext import commands
from src.clubbot.container import ServiceContainer


@pytest.mark.asyncio
async def test_container_wires_digits_enqueuer_when_redis_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Configure env for digits + redis
    monkeypatch.setenv("DISCORD_TOKEN", "x")
    monkeypatch.setenv("HANDWRITING_API_URL", "http://localhost:1234")
    monkeypatch.setenv("REDIS_URL", "redis://fake")

    # Stub the import used inside ServiceContainer.wire_bot_async
    mod = types.ModuleType("src.clubbot.services.jobs.digits_enqueuer")
    created: dict[str, object] = {}

    class _FakeRQDigitsEnqueuer:
        def __init__(self, *, redis_url: str, **_: object) -> None:
            created["redis_url"] = redis_url

    mod.RQDigitsEnqueuer = _FakeRQDigitsEnqueuer
    monkeypatch.setitem(
        __import__("sys").modules,
        "src.clubbot.services.jobs.digits_enqueuer",
        mod,
    )

    cont = ServiceContainer.from_env()
    intents = discord.Intents.default()
    bot = commands.Bot(command_prefix="!", intents=intents)
    await cont.wire_bot_async(bot)
    assert created.get("redis_url") == "redis://fake"
    assert "DigitsCog" in bot.cogs


@pytest.mark.asyncio
async def test_container_handles_missing_rq_digits_enqueuer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Configure env for digits + redis
    monkeypatch.setenv("DISCORD_TOKEN", "x")
    monkeypatch.setenv("HANDWRITING_API_URL", "http://localhost:1234")
    monkeypatch.setenv("REDIS_URL", "redis://fake")

    # Provide a module without RQDigitsEnqueuer to trigger the exception path
    empty_mod = types.ModuleType("src.clubbot.services.jobs.digits_enqueuer")
    monkeypatch.setitem(
        __import__("sys").modules,
        "src.clubbot.services.jobs.digits_enqueuer",
        empty_mod,
    )

    cont = ServiceContainer.from_env()
    intents = discord.Intents.default()
    bot = commands.Bot(command_prefix="!", intents=intents)
    # Should not raise even if enqueuer cannot be constructed
    await cont.wire_bot_async(bot)
    assert "DigitsCog" in bot.cogs
