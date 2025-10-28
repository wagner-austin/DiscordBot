from __future__ import annotations

import re
import urllib.parse as _url

from .errors import UserInputError

_YT_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "youtu.be",
    "www.youtu.be",
}


_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


def _extract_watch_id(parsed: _url.SplitResult) -> str | None:
    q = _url.parse_qs(parsed.query)
    vals = q.get("v")
    if not vals:
        return None
    first = vals[0]
    return first if isinstance(first, str) and first else None


def extract_video_id(url: str) -> str:
    """Return the YouTube video id from common URL shapes.

    Supports:
    - https://www.youtube.com/watch?v=<id>
    - https://youtu.be/<id>
    - https://www.youtube.com/shorts/<id>
    - https://www.youtube.com/live/<id>
    """
    raw = url.strip()
    if not raw:
        raise UserInputError("Please provide a YouTube URL")
    try:
        parsed = _url.urlsplit(raw if "://" in raw else f"https://{raw}")
    except Exception:
        raise UserInputError("Invalid YouTube URL format") from None

    host = parsed.netloc.lower()
    if host not in _YT_HOSTS:
        raise UserInputError("Only YouTube URLs are supported for /transcript")

    path = parsed.path.strip("/")
    vid: str | None = None
    if host in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
        if path == "watch":
            vid = _extract_watch_id(parsed)
        else:
            parts = path.split("/")
            if len(parts) >= 2 and parts[0] in {"shorts", "live"}:
                vid = parts[1]
    elif host in {"youtu.be", "www.youtu.be"}:
        parts = path.split("/")
        if parts and parts[0]:
            vid = parts[0]

    if not vid or not _VIDEO_ID_RE.match(vid):
        raise UserInputError("Could not extract a valid YouTube video id")
    return vid


def canonicalize_youtube_url(url: str) -> str:
    vid = extract_video_id(url)
    return f"https://www.youtube.com/watch?v={vid}"


def validate_youtube_url(url: str) -> str:
    """Validate and return canonical URL for a YouTube video."""
    return canonicalize_youtube_url(url)
