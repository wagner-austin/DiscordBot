import discord
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
    )


def test_qr_cog_can_be_added_to_bot():
    intents = discord.Intents.default()
    bot = commands.Bot(intents=intents)
    cfg = make_cfg()
    service = QRService(cfg)

    cog = QRCog(bot, cfg, service)
    bot.add_cog(cog)

    assert bot.get_cog("QRCog") is cog
