import logging
import os
import re
import tomllib
from collections.abc import Mapping as TypingMapping
from dataclasses import dataclass, field


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
    QR_STATS_ADMIN_USER_IDS: list[int] = field(default_factory=list)
    COMMANDS_SYNC_GLOBAL: bool = False
    # Transcript
    TRANSCRIPT_PUBLIC_RESPONSES: bool = False
    TRANSCRIPT_RATE_LIMIT: int = 2
    TRANSCRIPT_RATE_WINDOW_SECONDS: int = 60
    TRANSCRIPT_PREFERRED_LANGS: str = "en,en-US,en-GB"
    TRANSCRIPT_MAX_MESSAGE_CHARS: int = 1800
    YOUTUBE_API_KEY: str | None = None
    # Transcript provider selection: "youtube" (default) or "stt"
    TRANSCRIPT_PROVIDER: str = "youtube"
    # STT (OpenAI Whisper) configuration
    OPENAI_API_KEY: str | None = None
    TRANSCRIPT_MAX_VIDEO_SECONDS: int = 5400
    TRANSCRIPT_MAX_FILE_MB: int = 25
    TRANSCRIPT_STT_RTF: float = 0.5  # processing seconds per audio second
    TRANSCRIPT_DL_MIB_PER_SEC: float = 4.0
    TRANSCRIPT_STT_API_TIMEOUT_SECONDS: int = 900
    TRANSCRIPT_STT_API_MAX_RETRIES: int = 2
    TRANSCRIPT_COOKIES_TEXT: str | None = None
    TRANSCRIPT_COOKIES_PATH: str | None = None
    # Attachment constraints and estimates
    TRANSCRIPT_MAX_ATTACHMENT_MB: int = 25
    TRANSCRIPT_ESTIMATED_TEXT_KB_PER_MIN: float = 1.0
    # Chunking configuration
    TRANSCRIPT_ENABLE_CHUNKING: bool = True
    TRANSCRIPT_CHUNK_THRESHOLD_MB: float = 20.0
    TRANSCRIPT_TARGET_CHUNK_MB: float = 20.0
    TRANSCRIPT_MAX_CHUNK_DURATION_SECONDS: float = 600.0
    TRANSCRIPT_MAX_CONCURRENT_CHUNKS: int = 3
    TRANSCRIPT_SILENCE_THRESHOLD_DB: float = -40.0
    TRANSCRIPT_SILENCE_DURATION_SECONDS: float = 0.5
    # Job queue configuration (Redis BRPOP listener)
    JOB_QUEUE_BRPOP_TIMEOUT_SECONDS: int = 0  # 0 = indefinite block
    # RQ / Worker configuration
    REDIS_URL: str | None = None
    RQ_TRANSCRIPT_JOB_TIMEOUT_SEC: int = 600
    RQ_TRANSCRIPT_RESULT_TTL_SEC: int = 86400
    RQ_TRANSCRIPT_FAILURE_TTL_SEC: int = 604800
    RQ_TRANSCRIPT_RETRY_MAX: int = 2
    RQ_TRANSCRIPT_RETRY_INTERVALS_SEC: tuple[int, int] = (60, 300)
    TRANSCRIPT_EVENTS_CHANNEL: str = "transcript:events"
    TRANSCRIPT_RESULT_KEY_PREFIX: str = "transcript:result:"


def _parse_guilds() -> tuple[str | None, list[int]]:
    logger = logging.getLogger(__name__)
    single = os.getenv("DISCORD_GUILD_ID")
    multi = (os.getenv("DISCORD_GUILD_IDS", "") or "").strip()
    ids: list[int] = []
    if multi:
        for part in re.split(r"[\s,]+", multi):
            if not part:
                continue
            try:
                ids.append(int(part))
            except ValueError:
                logger.warning("Ignoring non-numeric guild id in DISCORD_GUILD_IDS: %s", part)
    elif single:
        try:
            ids.append(int(single))
        except ValueError:
            logger.warning("Invalid DISCORD_GUILD_ID value (not an integer): %s", single)
    return single, ids


# Helper readers that treat empty values as unset
def _s(name: str, default: str, *, upper: bool = False) -> str:
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


def _f(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _load_file_overrides() -> dict[str, object]:
    """Load config overrides from a TOML file if present.

    Precedence:
      - Path from CLUBBOT_CONFIG
      - ./clubbot.toml
      - ./config/clubbot.toml
    Keys should match Config field names (e.g., TRANSCRIPT_PROVIDER, OPENAI_API_KEY).
    Special: TRANSCRIPT_MAX_VIDEO_MINUTES is supported and converted to seconds.
    """
    candidates = [
        os.getenv("CLUBBOT_CONFIG", "").strip(),
        "clubbot.toml",
        os.path.join("config", "clubbot.toml"),
    ]
    for path in candidates:
        if path and os.path.isfile(path):
            try:
                with open(path, "rb") as f:
                    data = tomllib.load(f)
                if isinstance(data, dict):
                    return data
            except OSError:
                logging.getLogger(__name__).warning("Failed to read config file at %s", path)
                return {}
    return {}


def _from_overrides_int(
    overrides: TypingMapping[str, object], key: str, env_default: int, *, minutes: bool = False
) -> int:
    if key in overrides and overrides[key] is not None:
        try:
            val = int(str(overrides[key]).strip())
            return val * 60 if minutes else val
        except ValueError:
            return env_default
    return env_default


def load_config() -> Config:
    single_guild, guild_ids = _parse_guilds()
    file_overrides = _load_file_overrides()

    # Prefer OPENAI_API_KEY (standard); accept OPEN_AI_API_KEY; allow file override
    file_key = str(
        file_overrides.get("OPENAI_API_KEY") or file_overrides.get("OPEN_AI_API_KEY") or ""
    ).strip()
    openai_key = file_key or os.getenv("OPENAI_API_KEY") or os.getenv("OPEN_AI_API_KEY")

    # Use code default for transcript max length (no env or file override)
    secs_value = 5400

    # Parse RQ retry intervals as tuple[int, int]
    intervals_raw = os.getenv("RQ_TRANSCRIPT_RETRY_INTERVALS_SEC", "60,300").strip()
    parts = [p for p in re.split(r"[\s,]+", intervals_raw) if p]
    try:
        retry_intervals: tuple[int, int] = (
            (int(parts[0]), int(parts[1])) if len(parts) >= 2 else (60, 300)
        )
    except ValueError:
        retry_intervals = (60, 300)

    return Config(
        DISCORD_TOKEN=_s("DISCORD_TOKEN", ""),
        DISCORD_GUILD_ID=single_guild,
        DISCORD_GUILD_IDS=guild_ids,
        LOG_LEVEL=_s("LOG_LEVEL", "INFO", upper=True),
        QRCODE_RATE_LIMIT=_i("QRCODE_RATE_LIMIT", 1),
        QRCODE_RATE_WINDOW_SECONDS=_i("QRCODE_RATE_WINDOW_SECONDS", 1),
        QR_DEFAULT_ERROR_CORRECTION=str(
            file_overrides.get("QR_DEFAULT_ERROR_CORRECTION")
            or _s("QR_DEFAULT_ERROR_CORRECTION", "M", upper=True)
        ),
        QR_DEFAULT_BOX_SIZE=int(
            str(file_overrides.get("QR_DEFAULT_BOX_SIZE") or _i("QR_DEFAULT_BOX_SIZE", 10))
        ),
        QR_DEFAULT_BORDER=int(
            str(file_overrides.get("QR_DEFAULT_BORDER") or _i("QR_DEFAULT_BORDER", 1))
        ),
        QR_DEFAULT_FILL_COLOR=str(
            file_overrides.get("QR_DEFAULT_FILL_COLOR") or _s("QR_DEFAULT_FILL_COLOR", "#000000")
        ),
        QR_DEFAULT_BACK_COLOR=str(
            file_overrides.get("QR_DEFAULT_BACK_COLOR") or _s("QR_DEFAULT_BACK_COLOR", "#FFFFFF")
        ),
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
        TRANSCRIPT_PUBLIC_RESPONSES=os.getenv("TRANSCRIPT_PUBLIC_RESPONSES", "false")
        .strip()
        .lower()
        in {"1", "true", "yes", "y", "on"},
        TRANSCRIPT_RATE_LIMIT=int(
            str(file_overrides.get("TRANSCRIPT_RATE_LIMIT") or _i("TRANSCRIPT_RATE_LIMIT", 2))
        ),
        TRANSCRIPT_RATE_WINDOW_SECONDS=int(
            str(
                file_overrides.get("TRANSCRIPT_RATE_WINDOW_SECONDS")
                or _i("TRANSCRIPT_RATE_WINDOW_SECONDS", 60)
            )
        ),
        TRANSCRIPT_PREFERRED_LANGS=str(
            file_overrides.get("TRANSCRIPT_PREFERRED_LANGS")
            or os.getenv("TRANSCRIPT_PREFERRED_LANGS", "en,en-US,en-GB")
        ),
        TRANSCRIPT_MAX_MESSAGE_CHARS=int(
            str(
                file_overrides.get("TRANSCRIPT_MAX_MESSAGE_CHARS")
                or _i("TRANSCRIPT_MAX_MESSAGE_CHARS", 1800)
            )
        ),
        YOUTUBE_API_KEY=str(
            file_overrides.get("YOUTUBE_API_KEY") or (os.getenv("YOUTUBE_API_KEY") or None) or ""
        )
        or None,
        TRANSCRIPT_PROVIDER=str(
            file_overrides.get("TRANSCRIPT_PROVIDER") or os.getenv("TRANSCRIPT_PROVIDER", "youtube")
        )
        .strip()
        .lower()
        or "youtube",
        OPENAI_API_KEY=(openai_key or None),
        TRANSCRIPT_MAX_VIDEO_SECONDS=secs_value,
        TRANSCRIPT_MAX_FILE_MB=_from_overrides_int(
            file_overrides,
            "TRANSCRIPT_MAX_FILE_MB",
            _i("TRANSCRIPT_MAX_FILE_MB", 25),
        ),
        TRANSCRIPT_STT_RTF=float(
            str(file_overrides.get("TRANSCRIPT_STT_RTF") or _f("TRANSCRIPT_STT_RTF", 0.5))
        ),
        TRANSCRIPT_DL_MIB_PER_SEC=float(
            str(
                file_overrides.get("TRANSCRIPT_DL_MIB_PER_SEC")
                or _f("TRANSCRIPT_DL_MIB_PER_SEC", 4.0)
            )
        ),
        TRANSCRIPT_STT_API_TIMEOUT_SECONDS=_from_overrides_int(
            file_overrides,
            "TRANSCRIPT_STT_API_TIMEOUT_SECONDS",
            _i("TRANSCRIPT_STT_API_TIMEOUT_SECONDS", 900),
        ),
        TRANSCRIPT_STT_API_MAX_RETRIES=_from_overrides_int(
            file_overrides,
            "TRANSCRIPT_STT_API_MAX_RETRIES",
            _i("TRANSCRIPT_STT_API_MAX_RETRIES", 2),
        ),
        TRANSCRIPT_COOKIES_TEXT=(
            str(file_overrides.get("TRANSCRIPT_COOKIES_TEXT") or "").strip()
            or (os.getenv("TRANSCRIPT_COOKIES_TEXT") or "").strip()
            or None
        ),
        TRANSCRIPT_COOKIES_PATH=(
            str(file_overrides.get("TRANSCRIPT_COOKIES_PATH") or "").strip()
            or (os.getenv("TRANSCRIPT_COOKIES_PATH") or "").strip()
            or None
        ),
        TRANSCRIPT_MAX_ATTACHMENT_MB=int(
            str(
                file_overrides.get("TRANSCRIPT_MAX_ATTACHMENT_MB")
                or _i("TRANSCRIPT_MAX_ATTACHMENT_MB", 25)
            )
        ),
        TRANSCRIPT_ESTIMATED_TEXT_KB_PER_MIN=float(
            str(
                file_overrides.get("TRANSCRIPT_ESTIMATED_TEXT_KB_PER_MIN")
                or _f("TRANSCRIPT_ESTIMATED_TEXT_KB_PER_MIN", 1.0)
            )
        ),
        TRANSCRIPT_ENABLE_CHUNKING=(
            str(
                file_overrides.get("TRANSCRIPT_ENABLE_CHUNKING")
                or os.getenv("TRANSCRIPT_ENABLE_CHUNKING", "true")
            )
            .strip()
            .lower()
            in {"1", "true", "yes", "y", "on"}
        ),
        TRANSCRIPT_CHUNK_THRESHOLD_MB=float(
            str(
                file_overrides.get("TRANSCRIPT_CHUNK_THRESHOLD_MB")
                or _f("TRANSCRIPT_CHUNK_THRESHOLD_MB", 20.0)
            )
        ),
        TRANSCRIPT_TARGET_CHUNK_MB=float(
            str(
                file_overrides.get("TRANSCRIPT_TARGET_CHUNK_MB")
                or _f("TRANSCRIPT_TARGET_CHUNK_MB", 20.0)
            )
        ),
        TRANSCRIPT_MAX_CHUNK_DURATION_SECONDS=float(
            str(
                file_overrides.get("TRANSCRIPT_MAX_CHUNK_DURATION_SECONDS")
                or _f("TRANSCRIPT_MAX_CHUNK_DURATION_SECONDS", 600.0)
            )
        ),
        TRANSCRIPT_MAX_CONCURRENT_CHUNKS=int(
            str(
                file_overrides.get("TRANSCRIPT_MAX_CONCURRENT_CHUNKS")
                or _i("TRANSCRIPT_MAX_CONCURRENT_CHUNKS", 3)
            )
        ),
        TRANSCRIPT_SILENCE_THRESHOLD_DB=float(
            str(
                file_overrides.get("TRANSCRIPT_SILENCE_THRESHOLD_DB")
                or _f("TRANSCRIPT_SILENCE_THRESHOLD_DB", -40.0)
            )
        ),
        TRANSCRIPT_SILENCE_DURATION_SECONDS=float(
            str(
                file_overrides.get("TRANSCRIPT_SILENCE_DURATION_SECONDS")
                or _f("TRANSCRIPT_SILENCE_DURATION_SECONDS", 0.5)
            )
        ),
        JOB_QUEUE_BRPOP_TIMEOUT_SECONDS=_i("JOB_QUEUE_BRPOP_TIMEOUT_SECONDS", 0),
        REDIS_URL=str(file_overrides.get("REDIS_URL") or (os.getenv("REDIS_URL") or "")).strip()
        or None,
        RQ_TRANSCRIPT_JOB_TIMEOUT_SEC=_from_overrides_int(
            file_overrides,
            "RQ_TRANSCRIPT_JOB_TIMEOUT_SEC",
            _i("RQ_TRANSCRIPT_JOB_TIMEOUT_SEC", 600),
        ),
        RQ_TRANSCRIPT_RESULT_TTL_SEC=_from_overrides_int(
            file_overrides,
            "RQ_TRANSCRIPT_RESULT_TTL_SEC",
            _i("RQ_TRANSCRIPT_RESULT_TTL_SEC", 86400),
        ),
        RQ_TRANSCRIPT_FAILURE_TTL_SEC=_from_overrides_int(
            file_overrides,
            "RQ_TRANSCRIPT_FAILURE_TTL_SEC",
            _i("RQ_TRANSCRIPT_FAILURE_TTL_SEC", 604800),
        ),
        RQ_TRANSCRIPT_RETRY_MAX=_from_overrides_int(
            file_overrides,
            "RQ_TRANSCRIPT_RETRY_MAX",
            _i("RQ_TRANSCRIPT_RETRY_MAX", 2),
        ),
        RQ_TRANSCRIPT_RETRY_INTERVALS_SEC=retry_intervals,
        TRANSCRIPT_EVENTS_CHANNEL=str(
            file_overrides.get("TRANSCRIPT_EVENTS_CHANNEL")
            or os.getenv("TRANSCRIPT_EVENTS_CHANNEL", "transcript:events")
        ),
        TRANSCRIPT_RESULT_KEY_PREFIX=str(
            file_overrides.get("TRANSCRIPT_RESULT_KEY_PREFIX")
            or os.getenv("TRANSCRIPT_RESULT_KEY_PREFIX", "transcript:result:")
        ),
    )


def require_token(cfg: Config) -> None:
    if not cfg.DISCORD_TOKEN:
        logging.getLogger(__name__).error("DISCORD_TOKEN missing. Set it in your .env file.")
        raise RuntimeError("DISCORD_TOKEN is required. Set it in your .env file.")
