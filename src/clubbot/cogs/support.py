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

    @slash_cmd(
        description="Diagnose command availability and resync if needed (admins/officers)",
        contexts={
            InteractionContextType.guild,
            InteractionContextType.bot_dm,
            InteractionContextType.private_channel,
        },
    )
    async def diag(self, ctx: discord.ApplicationContext) -> None:
        # Gate to admins (ID list) or Officers
        user = getattr(ctx, "user", None)
        uid = getattr(user, "id", None)
        allow_ids = set(self.config.QR_STATS_ADMIN_USER_IDS or [])
        in_allow = uid is not None and uid in allow_ids
        in_officers = False
        if ctx.guild is not None:
            member = getattr(ctx, "author", None)
            in_officers = isinstance(member, discord.Member) and any(
                r.name.strip().lower() == self.config.QR_STATS_OFFICER_ROLE.strip().lower()
                for r in (getattr(member, "roles", []) or [])
            )
        if not (in_allow or in_officers):
            await ctx.respond("Only Officers or authorized admins can run /diag.", ephemeral=True)
            return

        # List registered commands from the client
        try:
            cmds = ctx.bot.application_commands or []
            names = sorted({c.name for c in cmds})
            info = f"Registered commands (unique {len(names)}): {names}"
        except Exception as e:
            info = f"Could not list commands: {e}"

        await ctx.respond(info, ephemeral=True)

    @slash_cmd(
        description="Force resync commands (admins/officers)",
        contexts={
            InteractionContextType.guild,
            InteractionContextType.bot_dm,
            InteractionContextType.private_channel,
        },
    )
    async def resync(self, ctx: discord.ApplicationContext) -> None:
        # Gate
        user = getattr(ctx, "user", None)
        uid = getattr(user, "id", None)
        allow_ids = set(self.config.QR_STATS_ADMIN_USER_IDS or [])
        in_allow = uid is not None and uid in allow_ids
        in_officers = False
        if ctx.guild is not None:
            member = getattr(ctx, "author", None)
            in_officers = isinstance(member, discord.Member) and any(
                r.name.strip().lower() == self.config.QR_STATS_OFFICER_ROLE.strip().lower()
                for r in (getattr(member, "roles", []) or [])
            )
        if not (in_allow or in_officers):
            await ctx.respond("Only Officers or authorized admins can run /resync.", ephemeral=True)
            return

        # Resync: per-guild when in a guild, else global
        try:
            if ctx.guild is not None:
                await ctx.bot.sync_commands(guild_ids=[ctx.guild.id])
                cmds = ctx.bot.application_commands or []
                names = sorted({c.name for c in cmds})
                await ctx.respond(
                    f"Per-guild resync complete for guild {ctx.guild.id}. Commands: {names}",
                    ephemeral=True,
                )
            else:
                await ctx.bot.sync_commands()
                cmds = ctx.bot.application_commands or []
                names = sorted({c.name for c in cmds})
                await ctx.respond(
                    f"Global resync complete. Commands: {names}",
                    ephemeral=True,
                )
        except Exception as e:
            await ctx.respond(f"Resync failed: {e}", ephemeral=True)
