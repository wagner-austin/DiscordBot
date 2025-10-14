import time
from io import BytesIO

import discord
from discord.ext import commands

from ..config import Config, load_config
from ..logging import set_request_id
from ..services.qr_app import QRService
from ..utils.discord_typing import slash_cmd
from ..utils.errors import UserInputError
from ..utils.rate_limiter import RateLimiter
from .base import BaseCog


class QRCog(BaseCog):
    def __init__(self, bot: commands.Bot, config: Config, qr_service: QRService) -> None:
        super().__init__()
        self.bot = bot
        self.config = config
        self.rate_limiter = RateLimiter(config.QRCODE_RATE_LIMIT)
        self.qr_service = qr_service

    @slash_cmd(description="Create a QR code from a URL")
    async def qrcode(
        self,
        ctx: discord.ApplicationContext,
        url: str,
    ) -> None:
        # Request-scoped logging
        req_id = self.new_request_id()
        set_request_id(req_id)
        log = self.request_logger(req_id)

        # Rate limit
        allowed, wait_seconds = self.rate_limiter.allow(ctx.user.id, "qrcode")
        if not allowed:
            await ctx.respond(
                f"Please wait {int(wait_seconds)} seconds before generating another QR code",
                ephemeral=True,
            )
            log.info("Rate limited user=%s", ctx.user.id)
            return

        try:
            # Generate image using injected service
            png_bytes = self.qr_service.generate_qr(url)

        except UserInputError as e:
            await self.handle_user_error(ctx, log, str(e))
            return
        except Exception as exc:
            await self.handle_exception(ctx, log, exc)
            return

        # Build filename qrcode_{timestamp}.png
        ts = int(time.time())
        filename = f"qrcode_{ts}.png"
        file = discord.File(fp=BytesIO(png_bytes), filename=filename)
        await ctx.respond(file=file, ephemeral=True)


def setup(bot: commands.Bot) -> None:
    # Extension entrypoint (fallback). Prefer DI from main.
    cfg = load_config()
    service = QRService(cfg)
    bot.add_cog(QRCog(bot, cfg, service))
