from __future__ import annotations

import contextlib
import logging

import discord
from discord import app_commands
from discord.ext import commands

from ..config import Config
from ..services.metrics import MetricsService, parse_window

TOP_DEFAULT: int = 10


class QRStatsCog(commands.Cog):
    def __init__(self, bot: commands.Bot, config: Config, metrics: MetricsService) -> None:
        super().__init__()
        self.bot = bot
        self.config = config
        self.metrics = metrics
        self.logger = logging.getLogger(__name__)

    def _has_officer_role(self, member: discord.Member | None) -> bool:
        if member is None:
            return False
        target = self.config.QR_STATS_OFFICER_ROLE.strip().lower()
        return any(r.name.strip().lower() == target for r in (getattr(member, "roles", []) or []))

    @app_commands.command(name="qrstats", description="Show QR generation stats (Officers only)")
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.allowed_installs(guilds=True, users=True)
    async def qrstats(self, interaction: discord.Interaction) -> None:
        self.logger.debug(
            "qrstats invoked: user=%s guild=%s admin_ids=%s default_window=%s",
            getattr(getattr(interaction, "user", None), "id", None),
            getattr(getattr(interaction, "guild", None), "id", None),
            self.config.QR_STATS_ADMIN_USER_IDS,
            self.config.QR_STATS_DEFAULT_WINDOW,
        )
        # Access control: Officers in guilds OR admin user IDs (works in DMs and guilds)
        user = getattr(interaction, "user", None)
        uid = getattr(user, "id", None)
        allow_ids = set(self.config.QR_STATS_ADMIN_USER_IDS or [])
        in_allow = uid is not None and uid in allow_ids

        in_officers = False
        if interaction.guild is not None:
            # In interactions, interaction.user is discord.Member in guilds
            member = interaction.user if isinstance(interaction.user, discord.Member) else None
            in_officers = self._has_officer_role(member)

        if not (in_allow or in_officers):
            self.logger.info(
                "qrstats denied: guild=%s user=%s (officers=%s, in_allow=%s)",
                getattr(getattr(interaction, "guild", None), "id", None),
                uid,
                in_officers,
                in_allow,
            )
            if interaction.response.is_done():
                await interaction.followup.send(
                    "Only Officers or authorized admins can view stats.", ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "Only Officers or authorized admins can view stats.", ephemeral=True
                )
            return

        # Defer quickly to avoid possible interaction timeouts
        with contextlib.suppress(Exception):
            await interaction.response.defer(ephemeral=True)

        win = parse_window(self.config.QR_STATS_DEFAULT_WINDOW)

        totals = self.metrics.summarize_totals(win)
        breakdown = self.metrics.outcome_breakdown(win)
        top_links = self.metrics.top_links(limit=TOP_DEFAULT, window_seconds=win)

        embed = discord.Embed(title="QR Stats", color=discord.Color.blurple())
        embed.add_field(name="Window", value=self.config.QR_STATS_DEFAULT_WINDOW, inline=True)
        embed.add_field(name="Total Attempts", value=str(totals["total_attempts"]), inline=True)
        embed.add_field(name="Total Success", value=str(totals["total_success"]), inline=True)
        embed.add_field(name="Unique Users", value=str(totals["unique_users"]), inline=True)
        embed.add_field(
            name="Unique Guilds (DMs included)",
            value=str(totals["unique_guilds"]),
            inline=True,
        )
        embed.add_field(name="Unique Links", value=str(totals["unique_links"]), inline=True)

        embed.add_field(
            name="Outcomes",
            value=(
                f"success: {breakdown['success']}\n"
                f"validation_fail: {breakdown['validation_fail']}\n"
                f"rate_limited: {breakdown['rate_limited']}\n"
                f"internal_error: {breakdown['internal_error']}"
            ),
            inline=False,
        )

        if top_links:
            lines = [f"{i+1}. {row['url']} - {row['count']}" for i, row in enumerate(top_links)]
            embed.add_field(name="Top Links", value="\n".join(lines)[:1024], inline=False)

        self.logger.info(
            "qrstats responded: guild=%s user=%s totals=%s",
            getattr(getattr(interaction, "guild", None), "id", None),
            uid,
            totals,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
