from __future__ import annotations

import asyncio
import logging
from enum import Enum, auto
from typing import TYPE_CHECKING

import discord
from discord import Intents
from discord.ext import commands  # For extension loading exceptions

from bot.core import telemetry

# from bot.core.containers import Container # Forward ref
from bot.core.discord.boot import MyBot
from bot.core.discord.di import initialize_and_wire_container
from bot.core.discord.events import register_event_handlers
from bot.core.discord.proxy import start_proxy_service_if_enabled, stop_proxy_service
from bot.core.settings import Settings
from bot.utils.module_discovery import iter_submodules

if TYPE_CHECKING:
    from bot.core.containers import Container

logger = logging.getLogger(__name__)


class LifecycleState(Enum):
    IDLE = auto()
    STARTING = auto()
    INITIALIZING_SERVICES = auto()
    LOADING_EXTENSIONS = auto()
    REGISTERING_HANDLERS = auto()
    CONNECTING_TO_DISCORD = auto()
    RUNNING = auto()  # Implicitly when bot.start() is running
    SHUTTING_DOWN = auto()
    STOPPED = auto()


class BotLifecycle:
    def __init__(self, settings: Settings):
        self._settings: Settings = settings
        self._state: LifecycleState = LifecycleState.IDLE
        self._bot: MyBot | None = None
        self._container: Container | None = None
        self._shutdown_event = asyncio.Event()
        # Bounded queue for runtime alerts that should be forwarded to the bot owner.
        self.alerts_q: asyncio.Queue[str] = asyncio.Queue(maxsize=settings.queues.alerts)

    @property
    def state(self) -> LifecycleState:
        return self._state

    def _set_state(self, new_state: LifecycleState) -> None:
        if self._state == new_state:
            return
        logger.info(f"Bot lifecycle state changing from {self._state.name} to {new_state.name}")
        self._state = new_state

    async def run(self) -> None:
        if self._state != LifecycleState.IDLE:
            logger.warning(
                f"Bot run() called when not in IDLE state (current: {self._state.name}). Ignoring."
            )
            return

        self._set_state(LifecycleState.STARTING)

        if not self._settings.discord_token:
            logger.critical("DISCORD_TOKEN is not set. Bot cannot start.")
            self._set_state(LifecycleState.STOPPED)
            return

        try:
            await self._initialize_services_and_bot()
            await self._load_extensions()
            self._register_event_handlers()  # This is synchronous
            # RUNNING state is implicitly managed by _connect_to_discord blocking call
            await self._connect_to_discord()

        except (KeyboardInterrupt, asyncio.CancelledError) as e:
            logger.info(
                f"Shutdown signal (KeyboardInterrupt/CancelledError: {type(e).__name__}) received."
            )
        except discord.errors.LoginFailure:
            logger.critical("Failed to log in to Discord. Check your DISCORD_TOKEN.")
            self._set_state(LifecycleState.STOPPED)
        except Exception as e:
            logger.exception(
                "An unexpected error occurred in the bot's main run cycle:", exc_info=e
            )
            self._set_state(LifecycleState.STOPPED)
        finally:
            await self.shutdown()

    async def _initialize_services_and_bot(self) -> None:
        self._set_state(LifecycleState.INITIALIZING_SERVICES)
        logger.info("Initializing services and bot instance...")

        # 📈  Start Prometheus exporter before other services spin up
        telemetry.start_exporter(self._settings.metrics_port)

        self._container = initialize_and_wire_container(
            app_settings=self._settings,
            runner_module_name=self.__module__,
        )

        intents = Intents.default()
        self._bot = MyBot(command_prefix="!", intents=intents, settings=self._settings)
        self._bot.container = self._container
        self._bot.lifecycle = self

        await start_proxy_service_if_enabled(self._container, self._bot)
        logger.info("Services and bot instance initialized.")

    async def _load_extensions(self) -> None:
        if not self._bot:
            logger.error("Bot not initialized, cannot load extensions.")
            raise RuntimeError("Bot not initialized for extension loading.")

        self._set_state(LifecycleState.LOADING_EXTENSIONS)
        logger.info("Loading extensions...")
        # Collect short cog names for summary line
        loaded: list[str] = []
        failed: list[str] = []

        # Ensure critical AlertPump extension is loaded even if command package is skipped
        try:
            await self._bot.load_extension("bot.plugins.commands.alert_pump")
        except commands.ExtensionAlreadyLoaded:
            pass
        except commands.ExtensionNotFound:
            logger.error("AlertPump extension not found – runtime alerts disabled!")
        except commands.ExtensionFailed as e:
            logger.exception("AlertPump extension failed to load", exc_info=e)

        for ext_name in iter_submodules("bot.plugins.commands"):
            # Skip since we loaded it explicitly
            if ext_name == "bot.plugins.commands.alert_pump":
                continue
            try:
                await self._bot.load_extension(ext_name)
                loaded.append(ext_name.rsplit(".", 1)[-1])
            except commands.ExtensionNotFound:
                failed.append(ext_name.rsplit(".", 1)[-1])
                logger.error(f"❌ Extension {ext_name} not found")
            except commands.NoEntryPointError:
                failed.append(ext_name.rsplit(".", 1)[-1])
                logger.error(f"❌ Extension {ext_name} has no setup() function.")
            except commands.ExtensionFailed as e:
                failed.append(ext_name.rsplit(".", 1)[-1])
                logger.error(f"❌ Extension {ext_name} failed: {e.original}")
            except Exception as e:
                failed.append(ext_name.rsplit(".", 1)[-1])
                logger.error(f"❌ Unexpected error loading {ext_name}: {e}")
        logger.info(
            f"🧩 Cogs loaded: {', '.join(loaded) or '—'}"
            + (f" | ❌ failed: {', '.join(failed)}" if failed else "")
        )

    def _register_event_handlers(self) -> None:
        if not self._bot:
            logger.error("Bot not initialized, cannot register event handlers.")
            raise RuntimeError("Bot not initialized for event handler registration.")

        self._set_state(LifecycleState.REGISTERING_HANDLERS)
        logger.info("Registering event handlers...")
        register_event_handlers(self._bot)
        logger.info("Event handlers registered.")

    async def _connect_to_discord(self) -> None:
        if not self._bot or not self._settings.discord_token:
            logger.error("Bot or token not available, cannot connect to Discord.")
            raise RuntimeError("Bot or token not available for Discord connection.")

        self._set_state(LifecycleState.CONNECTING_TO_DISCORD)
        logger.info("Attempting to connect the bot to Discord...")
        # This call is blocking until the bot is closed or an error occurs
        # Implicitly, state is RUNNING while this await is active
        await self._bot.start(self._settings.discord_token)
        logger.info("Bot has disconnected from Discord (bot.start() returned).")

    async def shutdown(self, signal_name: str | None = None) -> None:
        if self._state in [LifecycleState.SHUTTING_DOWN, LifecycleState.STOPPED]:
            # Avoid re-entrancy or multiple shutdown calls
            if self._state == LifecycleState.SHUTTING_DOWN:
                logger.info("Shutdown already in progress. Waiting for completion.")
                await self._shutdown_event.wait()
            return

        if signal_name:
            logger.info(f"Shutdown initiated by signal: {signal_name}.")
        else:
            logger.info("Shutdown initiated.")

        self._set_state(LifecycleState.SHUTTING_DOWN)

        logger.info("Attempting to gracefully shutdown services...")
        if self._bot:
            await stop_proxy_service(self._bot)
        logger.info("Finished service shutdown attempts.")

        if self._bot and not self._bot.is_closed():
            logger.info("Closing bot connection...")
            await self._bot.close()
            logger.info("Bot connection closed.")
        else:
            logger.info("Bot was already closed, not started, or not initialized.")

        self._set_state(LifecycleState.STOPPED)
        self._shutdown_event.set()
        logger.info("Bot has shut down.")

    async def wait_for_shutdown(self) -> None:
        await self._shutdown_event.wait()


# ------------------------------------------------------------------
# Global access hook (used by bot.core.alerts.send_alert)
# ------------------------------------------------------------------

_lifecycle_singleton: BotLifecycle | None = None
