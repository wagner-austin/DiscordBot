#!/usr/bin/env python
"""Start the Discord bot application.

Initialize logging and delegate execution to ``launch_bot``.
"""

from bot.core.launcher import launch_bot  # Import launch_bot from new launcher


async def main() -> None:
    """Asynchronous entry point for the bot.

    Configure logging then delegate to the startup orchestrator.
    """
    # Logging is configured during the initial bootstrap in bot.core.__main__.
    # The new launch_bot and BotLifecycle handle KeyboardInterrupt/CancelledError internally.
    await launch_bot()


# If this script were to be run directly (e.g. `python src/bot_core/main.py`),
# an asyncio.run(main()) call would be needed here, typically guarded by
# if __name__ == "__main__":.
# However, Poetry scripts handle the entry point invocation.
