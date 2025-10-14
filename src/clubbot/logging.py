import contextvars
import logging
import sys

REQUEST_ID_CTX: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


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


def setup_logging(level: str = "INFO") -> None:
    # Use force=True to ensure our config applies even if another library configured logging first.
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="[%(asctime)s] [%(levelname)s] [%(name)s] [req=%(request_id)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
        force=True,
    )
    # Add request-id filter to all handlers
    root = logging.getLogger()
    for handler in root.handlers:
        handler.addFilter(RequestIdFilter())
    # Quiet noisy third-party loggers by default
    logging.getLogger("discord").setLevel(logging.WARNING)
    logging.getLogger("discord.gateway").setLevel(logging.WARNING)
    logging.getLogger("discord.client").setLevel(logging.WARNING)
    logging.getLogger(__name__).debug("Logging configured at level %s", level.upper())
