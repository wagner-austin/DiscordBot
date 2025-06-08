#!/usr/bin/env python
"""
plugins/commands/shutdown.py
----------------------------
Summary: Shutdown command plugin. Shuts down the bot.
Usage:
  @bot shutdown
"""

from discord.ext import commands
from ..base import BaseCog
from bot.plugins.typing import Ctx


class Shutdown(BaseCog):
    @commands.command(name="shutdown")
    @commands.is_owner()
    async def shutdown(self, ctx: Ctx) -> None:
        """Cleanly shut the bot down (owner-only)."""
        await ctx.send("Bot is shutting down…")
        await ctx.bot.close()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Shutdown(bot))
