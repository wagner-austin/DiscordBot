import discord
import pytest
from discord.ext import commands
from src.clubbot.cogs.support import SupportCog
from src.clubbot.config import Config


class FakeCtx:
    def __init__(self, user_id: int = 1):
        self.user = type("User", (), {"id": user_id})()
        self.calls: list[dict] = []

    async def respond(self, message=None, embed=None, view=None, ephemeral=None):  # type: ignore[no-untyped-def]
        self.calls.append(
            {
                "message": message,
                "embed": embed,
                "view": view,
                "ephemeral": bool(ephemeral),
            }
        )


def make_cfg() -> Config:
    return Config(
        DISCORD_TOKEN="test",
        DISCORD_GUILD_ID=None,
        DISCORD_GUILD_IDS=[],
        LOG_LEVEL="DEBUG",
        QRCODE_RATE_LIMIT=1,
        QRCODE_RATE_WINDOW_SECONDS=1,
        QR_DEFAULT_ERROR_CORRECTION="M",
        QR_DEFAULT_BOX_SIZE=10,
        QR_DEFAULT_BORDER=2,
        QR_DEFAULT_FILL_COLOR="#000000",
        QR_DEFAULT_BACK_COLOR="#FFFFFF",
        QR_PUBLIC_RESPONSES=True,
        METRICS_ENABLED=False,
        METRICS_SQLITE_PATH="data/metrics.sqlite",
        METRICS_REDACT_QUERY=True,
        QR_STATS_OFFICER_ROLE="officers",
        QR_STATS_DEFAULT_WINDOW="7d",
        QR_STATS_ADMIN_USER_IDS=[],
        COMMANDS_SYNC_GLOBAL=False,
    )


@pytest.mark.asyncio
async def test_install_shows_buttons(monkeypatch):
    intents = discord.Intents.default()
    bot = commands.Bot(intents=intents)
    cog = SupportCog(bot, make_cfg())

    monkeypatch.setenv("DISCORD_APPLICATION_ID", "1234567890")
    ctx = FakeCtx()

    await cog.install.callback(cog, ctx)
    assert ctx.calls, "Expected respond called"
    last = ctx.calls[-1]
    assert isinstance(last["view"], discord.ui.View)
    # Two buttons present
    assert len(last["view"].children) >= 2
    labels = [b.label for b in last["view"].children if hasattr(b, "label")]
    assert "Enable DM Commands" in labels
    assert last["ephemeral"] is True
