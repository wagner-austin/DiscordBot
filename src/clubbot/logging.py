import contextvars
import logging
import os
import socket
import sys
import uuid

REQUEST_ID_CTX: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")
INSTANCE_ID: str | None = None


def set_request_id(request_id: str) -> None:
    REQUEST_ID_CTX.set(request_id)


class RequestIdFilter(logging.Filter):
    """Ensure every log record has a request_id attribute.

    This allows format strings to always reference %(request_id)s
    without KeyError, even when logs are outside request scope.
    """

    def filter(self, record: logging.LogRecord) -> bool:  # pragma: no cover - trivial
        record.request_id = REQUEST_ID_CTX.get()
        return True


class InstanceIdFilter(logging.Filter):
    """Attach a stable per-process instance_id to every record."""

    def __init__(self, instance_id: str) -> None:
        super().__init__()
        self.instance_id = instance_id

    def filter(self, record: logging.LogRecord) -> bool:  # pragma: no cover - trivial
        record.instance_id = self.instance_id
        return True


def _compute_instance_id() -> str:
    # Allow explicit override
    explicit = os.getenv("BOT_INSTANCE_ID", "").strip()
    if explicit:
        return explicit
    # Derive a short readable id from host, pid, and a short uuid
    host = socket.gethostname().split(".")[0]
    pid = os.getpid()
    suffix = uuid.uuid4().hex[:6]
    return f"{host}-{pid}-{suffix}"


def setup_logging(level: str = "INFO") -> None:
    # Use force=True to ensure our config applies even if another library configured logging first.
    global INSTANCE_ID
    INSTANCE_ID = _compute_instance_id()
    lvl = getattr(logging, level.upper(), logging.INFO)

    try:
        from rich.logging import RichHandler
        from rich.traceback import install as rich_install

        rich_install(show_locals=False)
        root = logging.getLogger()
        root.handlers.clear()
        root.setLevel(lvl)
        rich_handler: logging.Handler = RichHandler(
            rich_tracebacks=True, markup=True, show_time=True, show_level=True, show_path=False
        )
        rich_handler.setFormatter(
            logging.Formatter("%(message)s [inst=%(instance_id)s req=%(request_id)s]")
        )
        rich_handler.addFilter(RequestIdFilter())
        rich_handler.addFilter(InstanceIdFilter(INSTANCE_ID))
        root.addHandler(rich_handler)
    except (ImportError, Exception):
        logging.basicConfig(
            level=lvl,
            format=(
                "[%(asctime)s] [%(levelname)s] [%(name)s] "
                "[inst=%(instance_id)s req=%(request_id)s] %(message)s"
            ),
            datefmt="%Y-%m-%d %H:%M:%S",
            stream=sys.stdout,
            force=True,
        )
        # Add request-id filter to all handlers
        root = logging.getLogger()
        for handler in root.handlers:
            handler.addFilter(RequestIdFilter())
            handler.addFilter(InstanceIdFilter(INSTANCE_ID))

    # Quiet noisy third-party loggers by default
    logging.getLogger("discord").setLevel(logging.WARNING)
    logging.getLogger("discord.gateway").setLevel(logging.WARNING)
    logging.getLogger("discord.client").setLevel(logging.WARNING)
    # Reduce HTTP client verbosity
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpcore.http11").setLevel(logging.WARNING)
    logging.getLogger("httpcore.connection").setLevel(logging.WARNING)
    logging.getLogger(__name__).debug("Logging configured at level %s", level.upper())
    logging.getLogger(__name__).info("Bot instance id: %s", INSTANCE_ID)


def get_instance_id() -> str:
    return INSTANCE_ID or "-"
