from __future__ import annotations

import contextlib
import logging
import uuid
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

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
        # Use follow-up if we've already acknowledged (deferred/responded)
        fu = getattr(ctx, "followup", None)
        if getattr(ctx, "responded", False) and isinstance(fu, _FollowupLike):
            with contextlib.suppress(Exception):
                await fu.send(message, ephemeral=True)
            return
        await ctx.respond(message, ephemeral=True)

    async def handle_exception(
        self,
        ctx: discord.ApplicationContext,
        log: logging.LoggerAdapter[logging.Logger],
        exc: Exception,
    ) -> None:
        log.exception("Unhandled exception: %s", exc)
        # Prefer follow-up after a prior defer; otherwise initial respond
        fu = getattr(ctx, "followup", None)
        if getattr(ctx, "responded", False) and isinstance(fu, _FollowupLike):
            with contextlib.suppress(Exception):
                await fu.send("An error occurred. Please try again later.", ephemeral=True)
            return
        with contextlib.suppress(Exception):
            await ctx.respond("An error occurred. Please try again later.", ephemeral=True)


@runtime_checkable
class _FollowupLike(Protocol):
    async def send(self, *args: Any, **kwargs: Any) -> Any: ...
