from __future__ import annotations

from dotenv import find_dotenv, load_dotenv

from .container import ServiceContainer
from .logging import setup_logging
from .orchestrator import BotOrchestrator


def main() -> None:
    load_dotenv(find_dotenv(), override=True)
    container = ServiceContainer.from_env()
    setup_logging(container.cfg.LOG_LEVEL)
    BotOrchestrator(container).run()


if __name__ == "__main__":
    main()
