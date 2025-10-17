from __future__ import annotations

import time

import discord
from discord import app_commands
from discord.ext import commands

from ..config import Config, load_config
from ..logging import set_request_id
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

    @app_commands.command(name="ping", description="Simple ping to verify the bot is responsive")
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.allowed_installs(guilds=True, users=True)
    async def ping(self, interaction: discord.Interaction) -> None:
        req_id = self.new_request_id()
        set_request_id(req_id)
        log = self.request_logger(req_id)
        try:
            started = time.time()
            if interaction.response.is_done():
                await interaction.followup.send(f"Pong! req={req_id}")
            else:
                await interaction.response.send_message(f"Pong! req={req_id}")
            elapsed = int((time.time() - started) * 1000)
            log.info("Handled /ping in %sms", elapsed)
        except Exception as exc:  # pragma: no cover - trivial
            await self.handle_exception(interaction, log, exc)


async def setup(bot: commands.Bot) -> None:  # pragma: no cover - trivial
    cfg = load_config()
    await bot.add_cog(ExampleCog(bot, cfg))
