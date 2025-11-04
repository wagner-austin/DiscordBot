from __future__ import annotations

import types

import discord
import pytest
from discord.ext import commands
from src.clubbot.cogs.digits import DigitsCog
from src.clubbot.config import Config


class _FakeService:
    def __init__(self) -> None:
        self.max_image_bytes = 2 * 1024 * 1024


def _cfg() -> Config:
    return Config(
        DISCORD_TOKEN="t",
        DISCORD_GUILD_ID=None,
        DISCORD_GUILD_IDS=[],
        LOG_LEVEL="INFO",
        QRCODE_RATE_LIMIT=1,
        QRCODE_RATE_WINDOW_SECONDS=1,
        QR_DEFAULT_ERROR_CORRECTION="M",
        QR_DEFAULT_BOX_SIZE=10,
        QR_DEFAULT_BORDER=2,
        QR_DEFAULT_FILL_COLOR="#000000",
        QR_DEFAULT_BACK_COLOR="#FFFFFF",
        QR_PUBLIC_RESPONSES=True,
        REDIS_URL="redis://fake",
        DIGITS_PUBLIC_RESPONSES=False,
        DIGITS_RATE_LIMIT=2,
        DIGITS_RATE_WINDOW_SECONDS=60,
        DIGITS_MAX_IMAGE_MB=2,
    )


@pytest.mark.asyncio
async def test_digits_cog_events_subscriber_import_error(monkeypatch: pytest.MonkeyPatch) -> None:
    # Provide a module without the expected class name to trigger ImportError in from ... import ...
    empty_mod = types.ModuleType("src.clubbot.services.jobs.digits_notifier")
    monkeypatch.setitem(
        __import__("sys").modules,
        "src.clubbot.services.jobs.digits_notifier",
        empty_mod,
    )
    intents = discord.Intents.default()
    bot = commands.Bot(command_prefix="!", intents=intents)
    cfg = _cfg()
    svc = _FakeService()
    # Should not raise
    _ = DigitsCog(bot, cfg, svc)
