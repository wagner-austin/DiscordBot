from __future__ import annotations

from .container import ServiceContainer
from .logging import setup_logging
from .orchestrator import BotOrchestrator


def main() -> None:
    container = ServiceContainer.from_env()
    setup_logging(container.cfg.LOG_LEVEL)
    BotOrchestrator(container).run()


if __name__ == "__main__":
    main()
