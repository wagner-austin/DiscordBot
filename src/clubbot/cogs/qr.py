import time
from io import BytesIO

import discord
from discord.ext import commands

from ..config import Config, load_config
from ..logging import set_request_id
from ..services.qr_app import QRService
from ..services.qr_logic import build_effective_qr_options
from ..utils.discord_typing import slash_cmd
from ..utils.errors import UserInputError
from ..utils.rate_limiter import RateLimiter
from .base import BaseCog


class QRCog(BaseCog):
    def __init__(self, bot: commands.Bot, config: Config, qr_service: QRService) -> None:
        super().__init__()
        self.bot = bot
        self.config = config
        self.rate_limiter = RateLimiter(config.QRCODE_RATE_LIMIT, config.QRCODE_RATE_WINDOW_SECONDS)
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

        try:
            # Validate and normalize first (ensures clear user errors before rate-limiting)
            _ = build_effective_qr_options(url, self.config)

            # Apply rate limit (fast user feedback if limited)
            allowed, wait_seconds = self.rate_limiter.allow(ctx.user.id, "qrcode")
            if not allowed:
                await ctx.respond(
                    f"Please wait {int(wait_seconds)} seconds before generating another QR code",
                    ephemeral=not self.config.QR_PUBLIC_RESPONSES,
                )
                log.info("Rate limited user=%s", ctx.user.id)
                return

            # Defer to guarantee acks under 3s for slow generation
            if hasattr(ctx, "defer"):
                import contextlib

                with contextlib.suppress(Exception):
                    await ctx.defer(ephemeral=not self.config.QR_PUBLIC_RESPONSES)

            # Generate image using injected service
            result = self.qr_service.generate_qr(url)

        except UserInputError as e:
            await self.handle_user_error(ctx, log, str(e))
            return
        except Exception as exc:
            await self.handle_exception(ctx, log, exc)
            return

        # Build filename qrcode_{timestamp}.png
        ts = int(time.time())
        filename = f"qrcode_{ts}.png"
        file = discord.File(fp=BytesIO(result.image_png), filename=filename)
        # Place the URL as regular text above the image, with a blank line before and after
        # Use zero-width spaces before newlines to preserve blank lines in Discord
        content = f"\u200b\n🌐 <{result.url}>\n\u200b\n"
        content = f"\u200b\n🌐 <{result.url}>\n"
        await ctx.respond(content=content, file=file, ephemeral=not self.config.QR_PUBLIC_RESPONSES)


def setup(bot: commands.Bot) -> None:
    # Extension entrypoint (fallback). Prefer DI from main.
    cfg = load_config()
    service = QRService(cfg)
    bot.add_cog(QRCog(bot, cfg, service))
