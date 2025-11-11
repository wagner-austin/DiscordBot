from __future__ import annotations

import logging
from dataclasses import dataclass

from discord.ext import commands

from .config import Config, load_config, require_token
from .services.digits.app import DigitService
from .services.metrics import NullMetricsService, SQLiteMetricsService
from .services.qr_app import QRService
from .services.transcript.app import TranscriptService


@dataclass(frozen=True)
class ServiceContainer:
    """App-level dependency container.

    Holds configuration and constructed service singletons. Build once in main
    and pass dependencies explicitly to cogs/components.
    """

    cfg: Config
    qr_service: QRService
    metrics: SQLiteMetricsService | NullMetricsService
    transcript_service: TranscriptService | None = None
    digits_service: DigitService | None = None

    @classmethod
    def from_env(cls) -> ServiceContainer:
        cfg = load_config()
        require_token(cfg)
        qr_service = QRService(cfg)
        transcript_service = TranscriptService(cfg)
        digits_service = None
        if cfg.HANDWRITING_API_URL:
            digits_service = DigitService(cfg)
        if cfg.METRICS_ENABLED:
            metrics: SQLiteMetricsService | NullMetricsService = SQLiteMetricsService(
                sqlite_path=cfg.METRICS_SQLITE_PATH,
                redact_query=cfg.METRICS_REDACT_QUERY,
            )
        else:
            metrics = NullMetricsService()
        return cls(
            cfg=cfg,
            qr_service=qr_service,
            transcript_service=transcript_service,
            metrics=metrics,
            digits_service=digits_service,
        )

    # Bot wiring
    async def wire_bot_async(self, bot: commands.Bot) -> None:
        """Attach all cogs to the bot (idempotent)."""
        # Import locally to avoid import cycles at module import time
        from .cogs.digits import DigitsCog
        from .cogs.invite import InviteCog
        from .cogs.qr import QRCog
        from .cogs.trainer import TrainerCog
        from .cogs.transcript import TranscriptCog

        logger = logging.getLogger(__name__)

        if bot.get_cog("QRCog") is None:
            # Keep metrics available for future internal use; only QRCog is exposed.
            await bot.add_cog(QRCog(bot, self.cfg, self.qr_service))
            logger.info("Loaded cog: QRCog")
        if bot.get_cog("InviteCog") is None:
            await bot.add_cog(InviteCog(bot, self.cfg))
            logger.info("Loaded cog: InviteCog")
        if bot.get_cog("TranscriptCog") is None:
            svc = self.transcript_service or TranscriptService(self.cfg)
            await bot.add_cog(TranscriptCog(bot, self.cfg, svc))
            logger.info("Loaded cog: TranscriptCog")
        if self.digits_service is not None and bot.get_cog("DigitsCog") is None:
            # Optionally wire RQ enqueuer for digits training when REDIS_URL is set
            enqueuer = None
            redis_url = (getattr(self.cfg, "REDIS_URL", None) or "").strip()
            if redis_url:
                try:
                    from .services.jobs.digits_enqueuer import RQDigitsEnqueuer

                    enqueuer = RQDigitsEnqueuer(
                        redis_url=redis_url,
                        queue_name="digits",
                        job_timeout_s=25200,
                        result_ttl_s=86400,
                        failure_ttl_s=604800,
                        retry_max=2,
                        retry_intervals_s=(60, 300),
                    )
                except (RuntimeError, ValueError, ImportError, OSError, TypeError) as e:
                    logging.getLogger(__name__).warning(
                        "Failed to initialize digits RQ enqueuer: %s", e
                    )
                    enqueuer = None
            await bot.add_cog(DigitsCog(bot, self.cfg, self.digits_service, enqueuer=enqueuer))
            logger.info("Loaded cog: DigitsCog")
        # Trainer cog is always available when configured; it calls HTTP API directly
        if (self.cfg.MODEL_TRAINER_API_URL or "").strip() and bot.get_cog("TrainerCog") is None:
            await bot.add_cog(TrainerCog(bot, self.cfg))
            logger.info("Loaded cog: TrainerCog")
