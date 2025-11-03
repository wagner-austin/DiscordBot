from __future__ import annotations

import contextlib
import logging
import uuid
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

if TYPE_CHECKING:
    from typing import Protocol

    class _ResponseProto(Protocol):  # pragma: no cover - typing only
        def is_done(self) -> bool: ...

        async def send_message(self, *args: object, **kw: object) -> None: ...

    class _FollowupProto(Protocol):  # pragma: no cover - typing only
        async def send(self, *args: object, **kw: object) -> None: ...

    class _InteractionProto(Protocol):  # pragma: no cover - typing only
        @property
        def response(self) -> _ResponseProto: ...

        @property
        def followup(self) -> _FollowupProto: ...
else:  # pragma: no cover - runtime only
    _InteractionProto = object


class BaseCog(commands.Cog):
    """Shared base for cogs to provide request-scoped logging and helpers."""

    def __init__(self) -> None:
        super().__init__()
        self.logger = logging.getLogger(self.__class__.__module__)
        # Bot is injected by discord.py at runtime when the cog is added.
        # Keep loosely typed; concrete cogs can narrow.
        self.bot: object | None = None

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
        # Include request id for traceability in user message if available
        req_id = None
        extra = getattr(log, "extra", {})
        if isinstance(extra, dict):
            req_id = extra.get("request_id")
        suffix = f" (req={req_id})" if req_id else ""
        with contextlib.suppress(Exception):
            if interaction.response.is_done():
                await interaction.followup.send(
                    f"An error occurred{suffix}. Please try again later.", ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    f"An error occurred{suffix}. Please try again later.", ephemeral=True
                )

    async def notify_user(self, user_id: int, message: str) -> None:
        try:
            bot = getattr(self, "bot", None)
            if bot is None:
                return
            user = await bot.fetch_user(user_id)
            await user.send(message)
        except Exception:
            logging.getLogger(__name__).debug("Failed to DM user=%s", user_id)

    async def dm_file(self, user_id: int, content: str, file: discord.File) -> None:
        try:
            bot = getattr(self, "bot", None)
            if bot is None:
                return
            user = await bot.fetch_user(user_id)
            await user.send(content, file=file)
        except Exception:
            logging.getLogger(__name__).debug("Failed to DM file to user=%s", user_id)
