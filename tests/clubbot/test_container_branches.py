from __future__ import annotations

import discord
import pytest
from discord.ext import commands
from src.clubbot.container import ServiceContainer
from src.clubbot.services.metrics.sqlite import SQLiteMetricsService


@pytest.mark.asyncio
async def test_container_metrics_sqlite_and_digits_wiring(tmp_path, monkeypatch) -> None:
    # Configure env to enable metrics and digits
    monkeypatch.setenv("DISCORD_TOKEN", "x")
    monkeypatch.setenv("METRICS_ENABLED", "true")
    monkeypatch.setenv("METRICS_SQLITE_PATH", str(tmp_path / "metrics.sqlite"))
    monkeypatch.setenv("HANDWRITING_API_URL", "http://localhost:1234")
    # Keep other optional vars unset
    cont = ServiceContainer.from_env()
    assert isinstance(cont.metrics, SQLiteMetricsService)
    assert cont.digits_service is not None

    intents = discord.Intents.default()
    bot = commands.Bot(command_prefix="!", intents=intents)
    await cont.wire_bot_async(bot)
    assert "DigitsCog" in bot.cogs
