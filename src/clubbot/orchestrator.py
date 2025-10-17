from __future__ import annotations

import base64
import contextlib
import logging
import os
from collections.abc import Awaitable, Callable

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
        # Track a separate one-time global sync for DM availability
        self._has_synced_global: bool = False
        # Exposed listeners for tests (set in register_listeners)
        self._on_ready_listener: Callable[[], Awaitable[None]] | None = None
        self._on_guild_join_listener: Callable[[discord.Guild], Awaitable[None]] | None = None

    def build_bot(self) -> commands.Bot:
        intents = discord.Intents.default()
        # Enable message content if you see warnings about privileged intent.
        # This requires the Message Content Intent to be enabled in the Developer Portal.
        intents.message_content = True

        # discord.py manages app commands via bot.tree; override setup_hook for lifecycle wiring.
        container = self.container
        register_listeners = self.register_listeners

        class _Bot(commands.Bot):
            async def setup_hook(self) -> None:
                await container.wire_bot_async(self)
                register_listeners()

        self.bot = _Bot(command_prefix="!", intents=intents)
        return self.bot

    async def sync_commands(self) -> None:
        assert self.bot is not None
        cfg = self.container.cfg
        logger = self.logger
        try:
            # Global-only: commands are available in any guild and DMs.
            did_global = await self._sync_global()
            if not did_global:
                logger.info("Command sync is up-to-date; no changes applied")
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

    # Per-guild sync removed: we rely on global commands only.

    async def _sync_global(self) -> bool:
        assert self.bot is not None
        cfg = self.container.cfg
        logger = self.logger
        if not cfg.COMMANDS_SYNC_GLOBAL:
            return False
        if self._has_synced_global:
            logger.info("Global command sync already performed in this process; skipping")
            return False
        await self.bot.tree.sync()
        self._has_synced_global = True
        logger.info("Performed global command sync (DMs enabled; propagation may take time)")
        return True

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
            # Global commands are sufficient; no per-guild sync needed.

        async def on_application_command_error(
            interaction: discord.Interaction, error: Exception
        ) -> None:
            # The cog-level handlers already take care of most user errors;
            # this is a final catch-all.
            logger = logging.getLogger(__name__)
            original = getattr(error, "original", error)
            logger.exception("Unhandled application command error: %s", original)
            with contextlib.suppress(Exception):
                if interaction.response.is_done():
                    await interaction.followup.send(
                        "An error occurred. Please try again later.", ephemeral=True
                    )
                else:
                    await interaction.response.send_message(
                        "An error occurred. Please try again later.", ephemeral=True
                    )

        # Register listeners (no decorators to keep type-checkers happy)
        self.bot.add_listener(on_ready)
        self.bot.add_listener(on_connect)
        self.bot.add_listener(on_resumed)
        self.bot.add_listener(on_guild_join)
        self.bot.add_listener(on_application_command_error)
        # Expose for tests (avoid accessing internal listener tables)
        self._on_ready_listener = on_ready
        self._on_guild_join_listener = on_guild_join

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
        # Cog wiring and listener registration handled in setup_hook
        # Validate and run
        self._preflight_token_check()
        bot.run(self.container.cfg.DISCORD_TOKEN)
