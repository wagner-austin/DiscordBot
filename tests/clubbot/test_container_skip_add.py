from __future__ import annotations

import discord
import pytest
from discord.ext import commands
from src.clubbot.container import ServiceContainer


@pytest.mark.asyncio
async def test_wire_bot_skips_when_cogs_present(monkeypatch: pytest.MonkeyPatch) -> None:
    # Minimal env to satisfy require_token
    monkeypatch.setenv("DISCORD_TOKEN", "x")
    monkeypatch.setenv("METRICS_ENABLED", "false")
    cont = ServiceContainer.from_env()

    intents = discord.Intents.default()
    bot = commands.Bot(command_prefix="!", intents=intents)

    # Pre-register placeholder cogs with the expected names
    class QRCog(commands.Cog):
        def __init__(self) -> None:
            super().__init__()

    class InviteCog(commands.Cog):
        def __init__(self) -> None:
            super().__init__()

    class TranscriptCog(commands.Cog):
        def __init__(self) -> None:
            super().__init__()

    await bot.add_cog(QRCog())
    await bot.add_cog(InviteCog())
    await bot.add_cog(TranscriptCog())

    # Now wiring should detect existing cogs and not add duplicates
    await cont.wire_bot_async(bot)
    names = list(bot.cogs.keys())
    assert names.count("QRCog") == 1 and names.count("InviteCog") == 1
    assert names.count("TranscriptCog") == 1
