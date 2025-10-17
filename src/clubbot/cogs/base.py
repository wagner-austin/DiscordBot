from __future__ import annotations

import contextlib
import logging
import uuid
from typing import Any, Protocol, runtime_checkable

import discord
from discord.ext import commands


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
        interaction: discord.Interaction,
        log: logging.LoggerAdapter[logging.Logger],
        message: str,
    ) -> None:
        log.debug("User error: %s", message)
        try:
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.response.send_message(message, ephemeral=True)
        except Exception:
            with contextlib.suppress(Exception):
                await interaction.followup.send(message, ephemeral=True)

    async def handle_exception(
        self,
        interaction: discord.Interaction,
        log: logging.LoggerAdapter[logging.Logger],
        exc: Exception,
    ) -> None:
        log.exception("Unhandled exception: %s", exc)
        with contextlib.suppress(Exception):
            if interaction.response.is_done():
                await interaction.followup.send(
                    "An error occurred. Please try again later.", ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "An error occurred. Please try again later.", ephemeral=True
                )


@runtime_checkable
class _FollowupLike(Protocol):
    async def send(self, *args: Any, **kwargs: Any) -> Any: ...
