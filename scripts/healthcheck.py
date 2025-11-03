from __future__ import annotations

import os
import subprocess
import sys


def _ok(msg: str) -> None:
    sys.stdout.write(msg + "\n")


def _warn(msg: str) -> None:
    sys.stderr.write(msg + "\n")


def _has_cmd(name: str) -> bool:
    from shutil import which

    return which(name) is not None


def _check_discord_token() -> bool:
    tok = (os.getenv("DISCORD_TOKEN") or "").strip()
    if not tok:
        _warn("health: missing DISCORD_TOKEN")
        return False
    _ok("health: DISCORD_TOKEN present")
    return True


def _check_openai(provider: str) -> bool:
    if provider != "stt":
        return True
    openai_key = (os.getenv("OPENAI_API_KEY") or os.getenv("OPEN_AI_API_KEY") or "").strip()
    if not openai_key:
        _warn("health: TRANSCRIPT_PROVIDER=stt but OPENAI_API_KEY/OPEN_AI_API_KEY missing")
        return False
    _ok("health: OPENAI_API_KEY present for STT")
    return True


def _check_chunking(provider: str) -> bool:
    if provider != "stt":
        return True
    enable_chunk = os.getenv("TRANSCRIPT_ENABLE_CHUNKING", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "y",
        "on",
    }
    if not enable_chunk:
        return True
    if not _has_cmd("ffmpeg") or not _has_cmd("ffprobe"):
        _warn("health: chunking enabled but ffmpeg/ffprobe not found in PATH")
        return False
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True, timeout=5)
        _ok("health: ffmpeg available")
        return True
    except Exception:
        _warn("health: ffmpeg check failed")
        return False


def _check_redis(provider: str) -> bool:
    # Only required when background jobs are enabled (STT provider)
    if provider != "stt":
        return True
    redis_url = (os.getenv("REDIS_URL") or "").strip()
    if not redis_url:
        _warn("health: Redis not configured")
        return False
    try:
        import redis

        r = redis.Redis.from_url(redis_url, socket_timeout=5)
        if r.ping():
            _ok("health: Redis protocol reachable")
            return True
        _warn("health: Redis protocol ping failed")
        return False
    except Exception as e:
        _warn(f"health: Redis protocol check failed: {e}")
        return False


def _check_rq(provider: str) -> bool:
    if provider != "stt":
        return True
    try:
        from rq import Retry  # noqa: F401

        _ok("health: RQ import shape OK (top-level Retry)")
        return True
    except Exception as e:
        _warn(f"health: RQ import failed: {e}")
        return False


def main() -> int:
    ok = True
    ok &= _check_discord_token()
    provider = (os.getenv("TRANSCRIPT_PROVIDER") or "youtube").strip().lower()
    ok &= _check_openai(provider)
    ok &= _check_chunking(provider)
    ok &= _check_redis(provider)
    ok &= _check_rq(provider)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
