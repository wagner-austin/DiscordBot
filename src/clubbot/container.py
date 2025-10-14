from __future__ import annotations

from dataclasses import dataclass

from .config import Config, load_config, require_token
from .services.qr_app import QRService


@dataclass(frozen=True)
class ServiceContainer:
    """App-level dependency container.

    Holds configuration and constructed service singletons. Build once in main
    and pass dependencies explicitly to cogs/components.
    """

    cfg: Config
    qr_service: QRService

    @classmethod
    def from_env(cls) -> ServiceContainer:
        cfg = load_config()
        require_token(cfg)
        qr_service = QRService(cfg)
        return cls(cfg=cfg, qr_service=qr_service)

    # Bot wiring
    def wire_bot(self, bot) -> None:  # type: ignore[no-untyped-def]
        """Attach all cogs to the bot (idempotent)."""
        # Import locally to avoid import cycles at module import time
        from .cogs.qr import QRCog

        if bot.get_cog("QRCog") is None:
            bot.add_cog(QRCog(bot, self.cfg, self.qr_service))
