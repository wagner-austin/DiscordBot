from pathlib import Path

from dependency_injector import containers, providers

from bot.ai import providers as _ai_providers
from bot.browser.runtime import BrowserRuntime
from bot.core.settings import Settings
from bot.history.backends import HistoryBackend
from bot.history.in_memory import MemoryBackend
from bot.history.redis_backend import RedisBackend
from bot.infra.tankpit import engine_factory as tankpit_engine_factory
from bot.netproxy.service import ProxyService

# generic WebSocket addon and TankPit engine factory
from bot.netproxy.ws_addon import GenericWSAddon


class Container(containers.DeclarativeContainer):
    """Dependency Injection Container for the bot.

    This container holds providers for all core services and configurations.
    Services are typically registered as singletons to ensure a single instance
    is used throughout the application lifecycle.
    """

    # Configuration provider for application settings
    # The actual settings values will be loaded when accessed, typically from .env
    config = providers.Singleton(Settings)

    # Conversation history backend (pluggable)

    # Conversation history backend – pluggable
    @staticmethod
    def _choose_backend(cfg: Settings) -> HistoryBackend:
        redis_enabled = cfg.redis.enabled
        redis_url = cfg.redis.url
        import logging

        logger = logging.getLogger(__name__)
        import socket  # retained for backward-compat

        if redis_enabled and redis_url:
            logger.info("History backend: Redis (%s)", redis_url)
            try:
                return RedisBackend(redis_url, cfg.conversation_max_turns)
            except Exception as exc:
                logger.warning(
                    "Redis backend unreachable (%s), falling back to in-memory. Error: %s",
                    redis_url,
                    exc,
                )
        logger.info("History backend: In-memory (fallback)")
        return MemoryBackend(cfg.conversation_max_turns)

    history_backend: providers.Singleton[HistoryBackend] = providers.Singleton(
        _choose_backend, config
    )

    # Mapping of LLM provider singletons discovered in bot.ai.providers
    # Resolve the registry lazily so newly registered providers are seen.
    llm_providers = providers.Callable(lambda: _ai_providers.all())

    # Proxy service
    # The default_port and cert_dir for ProxyService can be sourced from config.
    # The 'addon' parameter defaults to None as per ProxyService.__init__ signature.
    # Proxy service
    proxy_service: providers.Singleton["ProxyService"] = providers.Singleton(
        ProxyService,
        port=providers.Callable(
            lambda cfg: cfg.proxy_port or 9000,  # Use OR for default
            config,
        ),
        certdir=providers.Callable(
            lambda cfg: Path(cfg.proxy_cert_dir),  # Path conversion is correct
            config,
        ),
        # Explicit list provider makes the "list-ness" clear and allows DI container
        # to resolve each element individually if they become providers themselves.
        addons=providers.List(
            providers.Object(GenericWSAddon),
        ),
        engine_factory=tankpit_engine_factory,
    )

    # Browser runtime – one process-wide instance wired through DI
    browser_runtime: providers.Singleton["BrowserRuntime"] = providers.Singleton(BrowserRuntime)


# Example of how to initialize and use the container (typically in main.py or discord_runner.py):
#
# if __name__ == '__main__':
#     container = Container()
#     container.config.load_dotenv() # If using .env files and pydantic-settings
#
#     # Wire up the container to cogs or other parts of the application
#     # For example, in discord_runner.py, you might do:
#     # container.wire(modules=[__name__, ".cogs.browser_cog_module_if_it_exists"])
#
#     engine = container.browser_engine()
#     runner = container.web_runner()
#     ps = container.proxy_service()
#
#     # Now engine, runner, ps are ready to be used or passed to cogs.
