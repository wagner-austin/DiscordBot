from __future__ import annotations

import contextlib
import logging
import uuid
from typing import TYPE_CHECKING

from discord.ext import commands

if TYPE_CHECKING:
    import discord


class BaseCog(commands.Cog):
    """Shared base for cogs to provide request-scoped logging and helpers."""

    def __init__(self) -> None:
        super().__init__()
        self.logger = logging.getLogger(self.__class__.__module__)

    @staticmethod
    def new_request_id() -> str:
        # Short, unique request id for correlating logs
        return uuid.uuid4().hex[:8]

    def request_logger(self, request_id: str) -> logging.LoggerAdapter[logging.Logger]:
        return logging.LoggerAdapter(self.logger, {"request_id": request_id})

    async def handle_user_error(
        self,
        ctx: discord.ApplicationContext,
        log: logging.LoggerAdapter[logging.Logger],
        message: str,
    ) -> None:
        log.debug("User error: %s", message)
        await ctx.respond(message, ephemeral=True)

    async def handle_exception(
        self,
        ctx: discord.ApplicationContext,
        log: logging.LoggerAdapter[logging.Logger],
        exc: Exception,
    ) -> None:
        log.exception("Unhandled exception: %s", exc)
        with contextlib.suppress(Exception):
            await ctx.respond("An error occurred. Please try again later.", ephemeral=True)
