from __future__ import annotations

import logging
from dataclasses import dataclass

from .config import Config, load_config, require_token
from .services.metrics import NullMetricsService, SQLiteMetricsService
from .services.qr_app import QRService


@dataclass(frozen=True)
class ServiceContainer:
    """App-level dependency container.

    Holds configuration and constructed service singletons. Build once in main
    and pass dependencies explicitly to cogs/components.
    """

    cfg: Config
    qr_service: QRService
    metrics: SQLiteMetricsService | NullMetricsService

    @classmethod
    def from_env(cls) -> ServiceContainer:
        cfg = load_config()
        require_token(cfg)
        qr_service = QRService(cfg)
        if cfg.METRICS_ENABLED:
            metrics: SQLiteMetricsService | NullMetricsService = SQLiteMetricsService(
                sqlite_path=cfg.METRICS_SQLITE_PATH,
                redact_query=cfg.METRICS_REDACT_QUERY,
            )
        else:
            metrics = NullMetricsService()
        return cls(cfg=cfg, qr_service=qr_service, metrics=metrics)

    # Bot wiring
    def wire_bot(self, bot) -> None:  # type: ignore[no-untyped-def]
        """Attach all cogs to the bot (idempotent)."""
        # Import locally to avoid import cycles at module import time
        from .cogs.qr import QRCog
        from .cogs.qr_stats import QRStatsCog
        from .cogs.support import SupportCog

        logger = logging.getLogger(__name__)

        if bot.get_cog("QRCog") is None:
            bot.add_cog(QRCog(bot, self.cfg, self.qr_service, self.metrics))
            logger.info("Loaded cog: QRCog")
        if bot.get_cog("QRStatsCog") is None:
            bot.add_cog(QRStatsCog(bot, self.cfg, self.metrics))
            logger.info("Loaded cog: QRStatsCog")
        if bot.get_cog("SupportCog") is None:
            bot.add_cog(SupportCog(bot, self.cfg))
            logger.info("Loaded cog: SupportCog (/install)")
