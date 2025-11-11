from __future__ import annotations

import discord
import pytest
from discord.ext import commands
from src.clubbot.container import ServiceContainer


@pytest.mark.asyncio
async def test_container_wires_trainer_cog(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISCORD_TOKEN", "x")
    monkeypatch.setenv("METRICS_ENABLED", "false")
    monkeypatch.setenv("MODEL_TRAINER_API_URL", "https://example")
    cont = ServiceContainer.from_env()
    intents = discord.Intents.default()
    bot = commands.Bot(command_prefix="!", intents=intents)
    await cont.wire_bot_async(bot)
    assert "TrainerCog" in bot.cogs
