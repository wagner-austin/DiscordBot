import re
import urllib.parse as _url

from PIL import ImageColor

from .errors import UserInputError

HEX_COLOR_PATTERN = re.compile(r"^#(?:[0-9a-fA-F]{3}){1,2}$")
DOMAIN_LABEL = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
DOMAIN_RE = re.compile(rf"^(?:{DOMAIN_LABEL}\.)+[A-Za-z]{{2,63}}$")
IPV4_RE = re.compile(r"^(?:\d{1,3}\.){3}\d{1,3}$")


def _normalize_url(url: str, default_scheme: str = "https") -> str:
    """Return a validated, normalized URL, adding a scheme when missing.

    Accepts inputs like "example.com", "www.example.com/path", or full
    "https://example.com". Only http/https are allowed. Raises UserInputError
    for invalid or overlong values.
    """
    raw = url.strip()
    if not raw:
        raise UserInputError("Please provide a URL")
    if len(raw) > 2000:
        raise UserInputError("URL is too long (max 2000 characters)")

    candidate = raw if "://" in raw else f"{default_scheme}://{raw}"
    try:
        parsed = _url.urlsplit(candidate)
    except Exception as _:
        raise UserInputError("Invalid URL format") from None

    if parsed.scheme.lower() not in {"http", "https"}:
        raise UserInputError("URL scheme must be http or https")

    netloc = parsed.netloc
    # Handle inputs like "example.com:8080"
    host = netloc
    if host.startswith("[") and "]" in host:
        # IPv6 like [::1] or [2001:db8::1]:port
        host = host.split("]", 1)[0] + "]"
    elif ":" in host:
        host = host.split(":", 1)[0]

    host_l = host.lower().strip(".")
    if not host_l:
        raise UserInputError("URL host is required (e.g., example.com)")

    valid_host = (
        host_l == "localhost"
        or DOMAIN_RE.match(host_l) is not None
        or IPV4_RE.match(host_l) is not None
        or (host_l.startswith("[") and host_l.endswith("]"))  # IPv6 literal
    )
    if not valid_host:
        raise UserInputError("Please provide a valid host (e.g., example.com)")

    # Recompose the normalized URL (ensures scheme present)
    return _url.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, ""))


def validate_url(url: str) -> str:
    return _normalize_url(url)


def validate_color(color: str | None, default: str) -> str:
    if not color:
        return default
    c = color.strip()
    if HEX_COLOR_PATTERN.match(c):
        return c
    # Allow PIL-named colors
    try:
        ImageColor.getrgb(c)
        return c
    except Exception as _:
        raise UserInputError(
            "Invalid color format. Use hex codes (e.g., #FF0000) or color names"
        ) from None


def validate_ecc(level: str | None, default: str) -> str:
    allowed = {"L", "M", "Q", "H"}
    if not level:
        return default
    up = level.upper()
    if up not in allowed:
        raise UserInputError("Invalid error correction. Choose one of: L, M, Q, H")
    return up


def validate_box_size(value: int | None, default: int) -> int:
    if value is None:
        return default
    if not (5 <= value <= 20):
        raise UserInputError("box_size must be between 5 and 20")
    return value


def validate_border(value: int | None, default: int) -> int:
    if value is None:
        return default
    if not (1 <= value <= 10):
        raise UserInputError("border must be between 1 and 10")
    return value
