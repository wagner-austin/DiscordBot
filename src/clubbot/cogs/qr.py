import asyncio
import contextlib
import logging
import time
from io import BytesIO
from typing import Any, cast

import discord
from discord import app_commands
from discord.ext import commands

from ..config import Config, load_config
from ..logging import set_request_id
from ..services.qr_app import QRService
from ..services.qr_logic import build_effective_qr_options
from ..utils.errors import UserInputError
from ..utils.rate_limiter import RateLimiter
from .base import BaseCog


class QRCog(BaseCog):
    def __init__(self, bot: commands.Bot, config: Config, qr_service: QRService) -> None:
        super().__init__()
        self.bot = bot
        self.config = config
        self.qr_service = qr_service
        # Per-user rate limiting to prevent rapid-fire requests
        self.rate_limiter = RateLimiter(config.QRCODE_RATE_LIMIT, config.QRCODE_RATE_WINDOW_SECONDS)

    @app_commands.command(name="qrcode", description="Create a QR code from a URL")
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.describe(url="URL to encode as a QR code")
    async def qrcode(self, interaction: discord.Interaction, url: str) -> None:
        # Ack first to avoid 3s timeout; silence stale/duplicates
        if not await self._ack_interaction(interaction):
            return

        # Request-scoped logging
        req_id = self.new_request_id()
        set_request_id(req_id)
        log = self.request_logger(req_id)
        user_id: int = cast(int, getattr(interaction.user, "id", None))
        log.debug("QR command invoked by user=%s for url=%s", user_id, url[:50])

        await self._process_qr(interaction, url, user_id, log)

    async def _ack_interaction(self, interaction: discord.Interaction) -> bool:
        """Acknowledge the interaction quickly; silence stale/duplicate cases."""
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=not self.config.QR_PUBLIC_RESPONSES)
            return True
        except discord.NotFound as e:
            logging.getLogger(__name__).debug(
                "Interaction expired before defer; skipping response: %s", e
            )
            return False
        except discord.HTTPException as e:
            # 40060: Interaction already acknowledged
            if getattr(e, "code", None) == 40060:
                logging.getLogger(__name__).debug(
                    "Interaction already acknowledged; continuing without defer"
                )
                return True
            logging.getLogger(__name__).exception("Failed to defer interaction: %s", e)
            with contextlib.suppress(Exception):
                await interaction.followup.send(
                    "An error occurred. Please try again.", ephemeral=True
                )
            return False
        except Exception as e:  # pragma: no cover - unexpected
            logging.getLogger(__name__).exception("Failed to defer interaction: %s", e)
            with contextlib.suppress(Exception):
                await interaction.followup.send(
                    "An error occurred. Please try again.", ephemeral=True
                )
            return False

    async def _process_qr(
        self,
        interaction: discord.Interaction,
        url: str,
        user_id: int,
        log: logging.LoggerAdapter[logging.Logger],
    ) -> None:
        try:
            # Validate and normalize URL
            opts = build_effective_qr_options(url, self.config)

            # Rate limit (fast feedback if limited)
            allowed, wait_seconds = self.rate_limiter.allow(user_id, "qrcode")
            if not allowed:
                await interaction.followup.send(
                    f"Please wait {int(wait_seconds)} seconds before generating another QR code",
                    ephemeral=not self.config.QR_PUBLIC_RESPONSES,
                )
                log.info("Rate limited user=%s", user_id)
                return

            # Generate image in a worker thread to avoid blocking the event loop
            result = await self._generate_qr_image(opts)

        except UserInputError as e:
            await self.handle_user_error(interaction, log, str(e))
            return
        except Exception as exc:
            await self.handle_exception(interaction, log, exc)
            return

        # Build filename qrcode_{timestamp}.png and send
        ts = int(time.time())
        filename = f"qrcode_{ts}.png"
        file = discord.File(fp=BytesIO(result.image_png), filename=filename)
        content = f"QR for <{result.url}>"
        await interaction.followup.send(
            content=content, file=file, ephemeral=not self.config.QR_PUBLIC_RESPONSES
        )
        log.info("QR code sent successfully for url=%s", result.url[:50])

    async def _generate_qr_image(self, opts: Any) -> Any:
        if hasattr(self.qr_service, "generate_qr_with_options"):
            return await asyncio.to_thread(self.qr_service.generate_qr_with_options, opts)
        gen = getattr(self.qr_service, "generate_qr", None)
        if callable(gen):
            return await asyncio.to_thread(gen, opts.url)
        raise RuntimeError("QR service missing generate method")


async def setup(bot: commands.Bot) -> None:
    cfg = load_config()
    service = QRService(cfg)
    await bot.add_cog(QRCog(bot, cfg, service))
