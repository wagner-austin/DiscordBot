import time
from io import BytesIO

import discord
from discord.enums import InteractionContextType
from discord.ext import commands

from ..config import Config, load_config
from ..logging import set_request_id
from ..services.metrics import (
    OUTCOME_INTERNAL_ERROR,
    OUTCOME_RATE_LIMITED,
    OUTCOME_SUCCESS,
    OUTCOME_VALIDATION_FAIL,
    NullMetricsService,
    QRGenerationOptions,
)
from ..services.metrics.service import MetricsService
from ..services.qr_app import QRService
from ..services.qr_logic import build_effective_qr_options
from ..utils.discord_typing import slash_cmd
from ..utils.errors import UserInputError
from ..utils.rate_limiter import RateLimiter
from .base import BaseCog


class QRCog(BaseCog):
    def __init__(
        self,
        bot: commands.Bot,
        config: Config,
        qr_service: QRService,
        metrics: MetricsService | NullMetricsService | None = None,
    ) -> None:
        super().__init__()
        self.bot = bot
        self.config = config
        self.rate_limiter = RateLimiter(config.QRCODE_RATE_LIMIT, config.QRCODE_RATE_WINDOW_SECONDS)
        self.qr_service = qr_service
        self.metrics = metrics or NullMetricsService()

    @slash_cmd(
        description="Create a QR code from a URL",
        contexts={
            InteractionContextType.guild,
            InteractionContextType.bot_dm,
            InteractionContextType.private_channel,
        },
    )
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
                # Log rate limit event
                self.metrics.log_qr_event(
                    outcome=OUTCOME_RATE_LIMITED,
                    ts=None,
                    user_id=ctx.user.id,
                    guild_id=(ctx.guild.id if getattr(ctx, "guild", None) else None),
                    input_url=url,
                    normalized_url=None,
                    options=QRGenerationOptions(
                        ecc=self.config.QR_DEFAULT_ERROR_CORRECTION,
                        box_size=self.config.QR_DEFAULT_BOX_SIZE,
                        border=self.config.QR_DEFAULT_BORDER,
                        fill_color=self.config.QR_DEFAULT_FILL_COLOR,
                        back_color=self.config.QR_DEFAULT_BACK_COLOR,
                    ),
                    public=self.config.QR_PUBLIC_RESPONSES,
                    error_type="rate_limited",
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
            # Log success event
            self.metrics.log_qr_event(
                outcome=OUTCOME_SUCCESS,
                ts=None,
                user_id=ctx.user.id,
                guild_id=(ctx.guild.id if getattr(ctx, "guild", None) else None),
                input_url=url,
                normalized_url=result.url,
                options=QRGenerationOptions(
                    ecc=self.config.QR_DEFAULT_ERROR_CORRECTION,
                    box_size=self.config.QR_DEFAULT_BOX_SIZE,
                    border=self.config.QR_DEFAULT_BORDER,
                    fill_color=self.config.QR_DEFAULT_FILL_COLOR,
                    back_color=self.config.QR_DEFAULT_BACK_COLOR,
                ),
                public=self.config.QR_PUBLIC_RESPONSES,
            )

        except UserInputError as e:
            await self.handle_user_error(ctx, log, str(e))
            # Log validation failure
            self.metrics.log_qr_event(
                outcome=OUTCOME_VALIDATION_FAIL,
                ts=None,
                user_id=ctx.user.id,
                guild_id=(ctx.guild.id if getattr(ctx, "guild", None) else None),
                input_url=url,
                normalized_url=None,
                options=QRGenerationOptions(
                    ecc=self.config.QR_DEFAULT_ERROR_CORRECTION,
                    box_size=self.config.QR_DEFAULT_BOX_SIZE,
                    border=self.config.QR_DEFAULT_BORDER,
                    fill_color=self.config.QR_DEFAULT_FILL_COLOR,
                    back_color=self.config.QR_DEFAULT_BACK_COLOR,
                ),
                public=self.config.QR_PUBLIC_RESPONSES,
                error_type="invalid_url",
                error_message=str(e),
            )
            return
        except Exception as exc:
            await self.handle_exception(ctx, log, exc)
            # Log internal error
            self.metrics.log_qr_event(
                outcome=OUTCOME_INTERNAL_ERROR,
                ts=None,
                user_id=ctx.user.id,
                guild_id=(ctx.guild.id if getattr(ctx, "guild", None) else None),
                input_url=url,
                normalized_url=None,
                options=QRGenerationOptions(
                    ecc=self.config.QR_DEFAULT_ERROR_CORRECTION,
                    box_size=self.config.QR_DEFAULT_BOX_SIZE,
                    border=self.config.QR_DEFAULT_BORDER,
                    fill_color=self.config.QR_DEFAULT_FILL_COLOR,
                    back_color=self.config.QR_DEFAULT_BACK_COLOR,
                ),
                public=self.config.QR_PUBLIC_RESPONSES,
                error_type="exception",
                error_message=exc.__class__.__name__,
            )
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
