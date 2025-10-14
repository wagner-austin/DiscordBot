from __future__ import annotations

import base64
import contextlib
import logging
import os
from collections.abc import Sequence

import discord
from discord.ext import commands

from .container import ServiceContainer


class BotOrchestrator:
    """Coordinates bot lifecycle: build, wire, listen, and run.

    - Builds the `commands.Bot` instance
    - Wires cogs via the ServiceContainer (pre-login; no lazy loading)
    - Registers event listeners
    - Validates token preflight and runs the bot
    - Handles command sync policy with per-guild fallback
    """

    def __init__(self, container: ServiceContainer) -> None:
        self.container = container
        self.bot: commands.Bot | None = None
        self.logger = logging.getLogger(__name__)
        # Sync bookkeeping to avoid hammering the commands endpoints on reconnects
        self._has_synced_once: bool = False
        self._last_present_ids: set[int] = set()

    def build_bot(self) -> commands.Bot:
        intents = discord.Intents.default()
        # Disable auto sync; we manage command sync manually per guild
        # to avoid duplicate syncs and rate-limit churn on startup.
        bot = commands.Bot(intents=intents, auto_sync_commands=False)
        # Belt-and-suspenders: ensure the runtime flag is off and log it.
        with contextlib.suppress(Exception):
            bot.auto_sync_commands = False
        logging.getLogger(__name__).info(
            "auto_sync_commands=%s (expected False)",
            getattr(bot, "auto_sync_commands", None),
        )
        self.bot = bot
        return bot

    async def sync_commands(self) -> None:
        assert self.bot is not None
        cfg = self.container.cfg
        logger = self.logger
        try:
            target_guilds: Sequence[int] = list(cfg.DISCORD_GUILD_IDS or [])
            if target_guilds:
                present_ids = [gid for gid in target_guilds if self.bot.get_guild(gid) is not None]
                missing_ids = [gid for gid in target_guilds if gid not in present_ids]

                if missing_ids:
                    logger.warning(
                        (
                            "Bot is not in guild(s) %s; skipping those. "
                            "Use the invite URL to add the bot."
                        ),
                        missing_ids,
                    )

                if present_ids:
                    # Skip if already synced these guilds in this process
                    current = set(present_ids)
                    if self._has_synced_once and current == self._last_present_ids:
                        logger.info("Command sync up-to-date; skipping per-guild sync")
                        return
                    await self.bot.sync_commands(guild_ids=present_ids)
                    logger.info("Synced commands to guilds %s", present_ids)
                    try:
                        names = sorted({c.name for c in (self.bot.application_commands or [])})
                        logger.info(
                            "Registered commands (per-guild, unique %s): %s",
                            len(names),
                            names,
                        )
                    except Exception as e:
                        logger.debug("Could not list application commands: %s", e)
                    self._last_present_ids = current
                    self._has_synced_once = True
                else:
                    logger.info("No present target guilds; skipping per-guild sync")
            else:
                logger.info("No target guilds configured")

            # Global sync disabled per simplification; commands are scoped to target guilds only.
        except discord.Forbidden as e:
            logger.error(
                (
                    "Missing access when syncing commands (guilds %s). Ensure the bot is invited "
                    "with applications.commands. Skipping global fallback. Error: %s"
                ),
                cfg.DISCORD_GUILD_IDS,
                e,
            )
        except discord.HTTPException as e:
            logger.exception("Failed to sync commands: %s", e)
            raise

    def register_listeners(self) -> None:
        assert self.bot is not None

        async def on_ready() -> None:
            logger = logging.getLogger(__name__)
            assert self.bot is not None
            logger.info(
                "Logged in as %s (ID: %s)",
                self.bot.user,
                self.bot.user and self.bot.user.id,
            )
            # Optionally perform startup sync if explicitly enabled.
            do_sync = os.getenv("COMMANDS_SYNC_ON_START", "false").strip().lower() in {
                "1",
                "true",
                "yes",
                "y",
                "on",
            }
            if do_sync:
                await self.sync_commands()
            else:
                logger.info("Startup command sync disabled; using existing registrations")

        async def on_connect() -> None:
            logging.getLogger(__name__).info("Gateway connected")

        async def on_resumed() -> None:
            logging.getLogger(__name__).info("Gateway resumed session")

        async def on_guild_join(guild: discord.Guild) -> None:
            logger = logging.getLogger(__name__)
            logger.info("Joined guild %s (%s)", guild.id, guild.name)
            try:
                cfg = self.container.cfg
                if cfg.DISCORD_GUILD_IDS and guild.id in cfg.DISCORD_GUILD_IDS:
                    assert self.bot is not None
                    await self.bot.sync_commands(guild_ids=[guild.id])
                    logger.info("Synced commands to newly joined guild %s", guild.id)
                else:
                    logger.info(
                        "Joined guild %s not in target list; skipping sync (no global fallback)",
                        guild.id,
                    )
            except discord.HTTPException as e:
                logger.exception("Failed to sync commands after joining guild %s: %s", guild.id, e)

        async def on_application_command_error(
            ctx: discord.ApplicationContext, error: Exception
        ) -> None:
            # The cog-level handlers already take care of most user errors;
            # this is a final catch-all.
            logger = logging.getLogger(__name__)
            original = getattr(error, "original", error)
            logger.exception("Unhandled application command error: %s", original)
            with contextlib.suppress(Exception):
                await ctx.respond("An error occurred. Please try again later.", ephemeral=True)

        # Register listeners (no decorators to keep type-checkers happy)
        self.bot.add_listener(on_ready)
        self.bot.add_listener(on_connect)
        self.bot.add_listener(on_resumed)
        self.bot.add_listener(on_guild_join)
        self.bot.add_listener(on_application_command_error)

    def _preflight_token_check(self) -> None:
        cfg = self.container.cfg
        token = cfg.DISCORD_TOKEN
        if token.startswith("Bot "):
            raise RuntimeError(
                "DISCORD_TOKEN should be the raw token string, without the 'Bot ' prefix."
            )
        app_id = os.getenv("DISCORD_APPLICATION_ID")
        if app_id:
            try:
                first = token.split(".")[0]
                padding = "=" * (-len(first) % 4)
                decoded = base64.b64decode(first + padding).decode("utf-8", errors="strict")
                if decoded != app_id:
                    raise RuntimeError(
                        "DISCORD_TOKEN appears to belong to a different application ID. "
                        "Verify you copied the Bot Token from the same application as "
                        "DISCORD_APPLICATION_ID."
                    )
            except Exception as exc:
                # Non-fatal; the library will still validate. Keep as debug detail.
                self.logger.debug("Could not verify token against application id: %s", exc)

    def run(self) -> None:
        # Build
        bot = self.build_bot()
        # Wire cogs before login (no lazy loading)
        self.container.wire_bot(bot)
        # Register listeners
        self.register_listeners()
        # Validate and run
        self._preflight_token_check()
        bot.run(self.container.cfg.DISCORD_TOKEN)
