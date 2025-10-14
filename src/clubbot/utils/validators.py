import re

from PIL import ImageColor

from .errors import UserInputError

HEX_COLOR_PATTERN = re.compile(r"^#(?:[0-9a-fA-F]{3}){1,2}$")
URL_PATTERN = re.compile(r"^https?://", re.IGNORECASE)


def validate_url(url: str) -> str:
    if not URL_PATTERN.match(url):
        raise UserInputError("Please provide a valid URL starting with http:// or https://")
    if len(url) > 2000:
        raise UserInputError("URL is too long (max 2000 characters)")
    return url


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
