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
    QR_STATS_ADMIN_USER_IDS: list[int] = None  # type: ignore[assignment]
    COMMANDS_SYNC_GLOBAL: bool = False


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

    # Helper readers that treat empty values as unset
    def _s(name: str, default: str, upper: bool = False) -> str:
        val = os.getenv(name)
        if val is None or val.strip() == "":
            val = default
        return val.upper() if upper else val

    def _i(name: str, default: int) -> int:
        raw = os.getenv(name)
        if raw is None or raw.strip() == "":
            return default
        try:
            return int(raw)
        except ValueError:
            return default

    return Config(
        DISCORD_TOKEN=_s("DISCORD_TOKEN", ""),
        DISCORD_GUILD_ID=single_guild,
        DISCORD_GUILD_IDS=guild_ids,
        LOG_LEVEL=_s("LOG_LEVEL", "INFO", upper=True),
        QRCODE_RATE_LIMIT=_i("QRCODE_RATE_LIMIT", 1),
        QRCODE_RATE_WINDOW_SECONDS=_i("QRCODE_RATE_WINDOW_SECONDS", 1),
        QR_DEFAULT_ERROR_CORRECTION=_s("QR_DEFAULT_ERROR_CORRECTION", "M", upper=True),
        QR_DEFAULT_BOX_SIZE=_i("QR_DEFAULT_BOX_SIZE", 10),
        QR_DEFAULT_BORDER=_i("QR_DEFAULT_BORDER", 1),
        QR_DEFAULT_FILL_COLOR=_s("QR_DEFAULT_FILL_COLOR", "#000000"),
        QR_DEFAULT_BACK_COLOR=_s("QR_DEFAULT_BACK_COLOR", "#FFFFFF"),
        QR_PUBLIC_RESPONSES=os.getenv("QR_PUBLIC_RESPONSES", "true").strip().lower()
        in {"1", "true", "yes", "y", "on"},
        METRICS_ENABLED=os.getenv("METRICS_ENABLED", "true").strip().lower()
        in {"1", "true", "yes", "y", "on"},
        METRICS_SQLITE_PATH=os.getenv("METRICS_SQLITE_PATH", "data/metrics.sqlite"),
        METRICS_REDACT_QUERY=os.getenv("METRICS_REDACT_QUERY", "true").strip().lower()
        in {"1", "true", "yes", "y", "on"},
        QR_STATS_OFFICER_ROLE=os.getenv("QR_STATS_OFFICER_ROLE", "officers"),
        QR_STATS_DEFAULT_WINDOW=os.getenv("QR_STATS_DEFAULT_WINDOW", "7d"),
        QR_STATS_ADMIN_USER_IDS=[
            int(x)
            for x in re.split(r"[\s,]+", os.getenv("QR_STATS_ADMIN_USER_IDS", "").strip())
            if x.isdigit()
        ],
        COMMANDS_SYNC_GLOBAL=os.getenv("COMMANDS_SYNC_GLOBAL", "false").strip().lower()
        in {"1", "true", "yes", "y", "on"},
    )


def require_token(cfg: Config) -> None:
    if not cfg.DISCORD_TOKEN:
        logging.getLogger(__name__).error("DISCORD_TOKEN missing. Set it in your .env file.")
        raise RuntimeError("DISCORD_TOKEN is required. Set it in your .env file.")
