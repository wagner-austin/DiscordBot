import asyncio
import contextlib
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
        self.qr_service = qr_service
        # Reintroduce per-user rate limiting to prevent rapid-fire requests
        self.rate_limiter = RateLimiter(config.QRCODE_RATE_LIMIT, config.QRCODE_RATE_WINDOW_SECONDS)

    @slash_cmd(description="Create a QR code from a URL")
    async def qrcode(self, ctx: discord.ApplicationContext, url: str) -> None:
        req_id = self.new_request_id()
        set_request_id(req_id)
        log = self.request_logger(req_id)

        log.debug("QR command invoked by user=%s for url=%s", ctx.user.id, url[:50])

        # Defer immediately to prevent interaction timeout (when supported by context)
        if hasattr(ctx, "defer"):
            log.debug("Attempting to defer interaction")
            try:
                await ctx.defer(ephemeral=not self.config.QR_PUBLIC_RESPONSES)
                log.debug("Successfully deferred interaction")
            except discord.NotFound as e:
                log.error("Interaction already expired before defer: %s", e)
                # Try to respond anyway (will likely fail but worth attempting)
                with contextlib.suppress(Exception):
                    await ctx.respond("Request timed out. Please try again.", ephemeral=True)
                with contextlib.suppress(Exception):
                    await ctx.user.send(
                        "Your slash command request expired before the bot could respond. "
                        "Please try again. If this keeps happening, reload Discord (Ctrl+R)."
                    )
                return
            except Exception as e:
                log.exception("Failed to defer interaction: %s", e)
                # Try to respond with error
                with contextlib.suppress(Exception):
                    await ctx.respond("An error occurred. Please try again.", ephemeral=True)
                return
        else:
            log.debug("Context has no defer(); skipping initial ACK")

        try:
            # Validate and normalize URL
            opts = build_effective_qr_options(url, self.config)

            # Apply rate limit (fast user feedback if limited)
            allowed, wait_seconds = self.rate_limiter.allow(ctx.user.id, "qrcode")
            if not allowed:
                await ctx.respond(
                    f"Please wait {int(wait_seconds)} seconds before generating another QR code",
                    ephemeral=not self.config.QR_PUBLIC_RESPONSES,
                )
                log.info("Rate limited user=%s", ctx.user.id)
                return

            # Generate image in a worker thread to avoid blocking the event loop
            if hasattr(self.qr_service, "generate_qr_with_options"):
                result = await asyncio.to_thread(
                    self.qr_service.generate_qr_with_options,
                    opts,
                )
            else:
                # Test doubles may expose a simpler API: generate_qr(url)
                gen = getattr(self.qr_service, "generate_qr", None)
                if callable(gen):
                    result = await asyncio.to_thread(gen, opts.url)
                else:
                    raise RuntimeError("QR service missing generate method")

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
        # Regular text above the image, with a single blank line before.
        # Use a zero-width space before the newline to preserve the blank line in Discord.
        content = f"\u200b\n🌐 <{result.url}>\n"
        content = f"QR for <{result.url}>"
        await ctx.respond(content=content, file=file, ephemeral=not self.config.QR_PUBLIC_RESPONSES)
        log.info("QR code sent successfully for url=%s", result.url[:50])


def setup(bot: commands.Bot) -> None:
    cfg = load_config()
    service = QRService(cfg)
    bot.add_cog(QRCog(bot, cfg, service))
