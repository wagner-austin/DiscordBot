from __future__ import annotations

import os

import discord
from discord.enums import InteractionContextType
from discord.ext import commands

from ..config import Config
from ..utils.discord_typing import slash_cmd


def build_user_install_link(app_id: str) -> str:
    return f"https://discord.com/oauth2/authorize?client_id={app_id}&scope=applications.commands"


class SupportCog(commands.Cog):
    def __init__(self, bot: commands.Bot, config: Config) -> None:
        super().__init__()
        self.bot = bot
        self.config = config

    @slash_cmd(
        description="Get links to enable DM commands",
        contexts={
            InteractionContextType.guild,
            InteractionContextType.bot_dm,
            InteractionContextType.private_channel,
        },
    )
    async def install(self, ctx: discord.ApplicationContext) -> None:
        # Log invocation for debugging
        import logging

        logging.getLogger(__name__).debug(
            "/install invoked by user=%s",
            getattr(getattr(ctx, "user", None), "id", None),
        )
        app_id = os.getenv("DISCORD_APPLICATION_ID", "").strip()
        if not app_id:
            await ctx.respond(
                "Missing DISCORD_APPLICATION_ID; ask an admin to configure the app.",
                ephemeral=True,
            )
            return

        user_install = build_user_install_link(app_id)

        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="Enable DM Commands", url=user_install))
        view.add_item(discord.ui.Button(label="Open DMs", url="https://discord.com/channels/@me"))

        await ctx.respond(
            "Use these to enable DM slash commands and open your DMs:",
            view=view,
            ephemeral=True,
        )
