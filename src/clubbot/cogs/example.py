from __future__ import annotations

import time

import discord
from discord.ext import commands

from ..config import Config, load_config
from ..logging import set_request_id
from ..utils.discord_typing import slash_cmd
from .base import BaseCog


class ExampleCog(BaseCog):
    """Minimal example cog using BaseCog with request-scoped logging.

    Not auto-loaded. To try it, call:
      bot.load_extension("clubbot.cogs.example")
    """

    def __init__(self, bot: commands.Bot, config: Config) -> None:
        super().__init__()
        self.bot = bot
        self.config = config

    @slash_cmd(description="Simple ping to verify the bot is responsive")
    async def ping(self, ctx: discord.ApplicationContext) -> None:
        req_id = self.new_request_id()
        set_request_id(req_id)
        log = self.request_logger(req_id)
        try:
            started = time.time()
            await ctx.respond(f"Pong! req={req_id}")
            elapsed = int((time.time() - started) * 1000)
            log.info("Handled /ping in %sms", elapsed)
        except Exception as exc:  # pragma: no cover - trivial
            await self.handle_exception(ctx, log, exc)


def setup(bot: commands.Bot) -> None:  # pragma: no cover - trivial
    cfg = load_config()
    bot.add_cog(ExampleCog(bot, cfg))
