import os

import discord
from discord import app_commands
from discord.ext import commands

from ..config import Config
from .base import BaseCog


def _resolve_app_id(client: commands.Bot) -> int | None:
    # Prefer runtime application_id if available, fallback to bot user id, then env
    app_id = getattr(client, "application_id", None)
    if app_id:
        return int(app_id)
    user = getattr(client, "user", None)
    if user is not None and getattr(user, "id", None) is not None:
        return int(user.id)
    env_id = os.getenv("DISCORD_APPLICATION_ID")
    if env_id and env_id.isdigit():
        return int(env_id)
    return None


class InviteCog(BaseCog):
    def __init__(self, bot: commands.Bot, config: Config) -> None:
        super().__init__()
        self.bot = bot
        self.config = config

    @app_commands.command(name="invite", description="Get the server invite link for this bot")
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.allowed_installs(guilds=True, users=True)
    async def invite(self, interaction: discord.Interaction) -> None:
        app_id = _resolve_app_id(self.bot)
        if app_id is None:
            await interaction.response.send_message(
                "Could not determine application id for this bot.", ephemeral=True
            )
            return

        perms = os.getenv("DISCORD_PERMISSIONS", "2147601408")
        guild_url = (
            f"https://discord.com/api/oauth2/authorize?client_id={app_id}"
            f"&permissions={perms}&scope=bot%20applications.commands"
        )
        embed = discord.Embed(title="Invite Link", color=discord.Color.blurple())
        embed.add_field(name="Guild Install (server admins)", value=guild_url, inline=False)

        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)
