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


def main() -> int:
    ok = True

    # Required token
    if not (os.getenv("DISCORD_TOKEN") or "").strip():
        _warn("health: missing DISCORD_TOKEN")
        ok = False
    else:
        _ok("health: DISCORD_TOKEN present")

    provider = (os.getenv("TRANSCRIPT_PROVIDER") or "youtube").strip().lower()
    if provider == "stt":
        # Check both OPENAI_API_KEY and OPEN_AI_API_KEY (like config.py does)
        openai_key = (os.getenv("OPENAI_API_KEY") or os.getenv("OPEN_AI_API_KEY") or "").strip()
        if not openai_key:
            _warn("health: TRANSCRIPT_PROVIDER=stt but OPENAI_API_KEY/OPEN_AI_API_KEY missing")
            ok = False
        else:
            _ok("health: OPENAI_API_KEY present for STT")

    enable_chunk = os.getenv("TRANSCRIPT_ENABLE_CHUNKING", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "y",
        "on",
    }
    if provider == "stt" and enable_chunk:
        # Require ffmpeg/ffprobe for chunking
        if not _has_cmd("ffmpeg") or not _has_cmd("ffprobe"):
            _warn("health: chunking enabled but ffmpeg/ffprobe not found in PATH")
            ok = False
        else:
            try:
                subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True, timeout=5)
                _ok("health: ffmpeg available")
            except Exception:
                _warn("health: ffmpeg check failed")
                ok = False

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
