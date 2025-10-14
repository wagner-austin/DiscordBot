import logging
import os
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    DISCORD_TOKEN: str
    DISCORD_GUILD_ID: str | None
    DISCORD_GUILD_IDS: list[int]
    LOG_LEVEL: str
    QRCODE_RATE_LIMIT: int
    QRCODE_RATE_WINDOW_SECONDS: int
    QR_DEFAULT_ERROR_CORRECTION: str
    QR_DEFAULT_BOX_SIZE: int
    QR_DEFAULT_BORDER: int
    QR_DEFAULT_FILL_COLOR: str
    QR_DEFAULT_BACK_COLOR: str
    QR_PUBLIC_RESPONSES: bool
    # Metrics / Stats
    METRICS_ENABLED: bool = True
    METRICS_SQLITE_PATH: str = "data/metrics.sqlite"
    METRICS_REDACT_QUERY: bool = True
    QR_STATS_OFFICER_ROLE: str = "officers"
    QR_STATS_DEFAULT_WINDOW: str = "7d"


def load_config() -> Config:
    logger = logging.getLogger(__name__)
    single_guild = os.getenv("DISCORD_GUILD_ID")
    multi_env = os.getenv("DISCORD_GUILD_IDS", "").strip()

    guild_ids: list[int] = []
    if multi_env:
        for part in re.split(r"[\s,]+", multi_env):
            if not part:
                continue
            try:
                guild_ids.append(int(part))
            except ValueError:
                logger.warning("Ignoring non-numeric guild id in DISCORD_GUILD_IDS: %s", part)
    elif single_guild:
        try:
            guild_ids.append(int(single_guild))
        except ValueError:
            logger.warning(
                "Invalid DISCORD_GUILD_ID value (not an integer): %s",
                single_guild,
            )

    return Config(
        DISCORD_TOKEN=os.getenv("DISCORD_TOKEN", ""),
        DISCORD_GUILD_ID=single_guild,
        DISCORD_GUILD_IDS=guild_ids,
        LOG_LEVEL=os.getenv("LOG_LEVEL", "INFO").upper(),
        QRCODE_RATE_LIMIT=int(os.getenv("QRCODE_RATE_LIMIT", "1")),
        QRCODE_RATE_WINDOW_SECONDS=int(os.getenv("QRCODE_RATE_WINDOW_SECONDS", "1")),
        QR_DEFAULT_ERROR_CORRECTION=os.getenv("QR_DEFAULT_ERROR_CORRECTION", "M").upper(),
        QR_DEFAULT_BOX_SIZE=int(os.getenv("QR_DEFAULT_BOX_SIZE", "10")),
        QR_DEFAULT_BORDER=int(os.getenv("QR_DEFAULT_BORDER", "1")),
        QR_DEFAULT_FILL_COLOR=os.getenv("QR_DEFAULT_FILL_COLOR", "#000000"),
        QR_DEFAULT_BACK_COLOR=os.getenv("QR_DEFAULT_BACK_COLOR", "#FFFFFF"),
        QR_PUBLIC_RESPONSES=os.getenv("QR_PUBLIC_RESPONSES", "true").strip().lower()
        in {"1", "true", "yes", "y", "on"},
        METRICS_ENABLED=os.getenv("METRICS_ENABLED", "true").strip().lower()
        in {"1", "true", "yes", "y", "on"},
        METRICS_SQLITE_PATH=os.getenv("METRICS_SQLITE_PATH", "data/metrics.sqlite"),
        METRICS_REDACT_QUERY=os.getenv("METRICS_REDACT_QUERY", "true").strip().lower()
        in {"1", "true", "yes", "y", "on"},
        QR_STATS_OFFICER_ROLE=os.getenv("QR_STATS_OFFICER_ROLE", "officers"),
        QR_STATS_DEFAULT_WINDOW=os.getenv("QR_STATS_DEFAULT_WINDOW", "7d"),
    )


def require_token(cfg: Config) -> None:
    if not cfg.DISCORD_TOKEN:
        logging.getLogger(__name__).error("DISCORD_TOKEN missing. Set it in your .env file.")
        raise RuntimeError("DISCORD_TOKEN is required. Set it in your .env file.")
