import discord
import pytest
from discord.ext import commands
from src.clubbot.cogs.qr import QRCog
from src.clubbot.config import Config
from src.clubbot.services.qr_app import QRService


def make_cfg() -> Config:
    return Config(
        DISCORD_TOKEN="test",
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
    )


@pytest.mark.asyncio
async def test_qrcode_metadata_allows_dms_and_user_installs():
    intents = discord.Intents.default()
    bot = commands.Bot(command_prefix="!", intents=intents)
    cfg = make_cfg()
    service = QRService(cfg)

    await bot.add_cog(QRCog(bot, cfg, service))

    cmds = {c.name: c for c in bot.tree.get_commands()}
    assert "qrcode" in cmds, "qrcode command not registered on app command tree"
    cmd = cmds["qrcode"]

    # Validate contexts include DM/guild via allowed_contexts (discord.py 2.4)
    assert cmd.allowed_contexts is not None
    ctxs = cmd.allowed_contexts
    assert ctxs.guild is True
    assert ctxs.dm_channel is True
    assert ctxs.private_channel is True

    # Validate installs include user and guild via allowed_installs
    assert cmd.allowed_installs is not None
    inst = cmd.allowed_installs
    assert inst.user is True
    assert inst.guild is True
