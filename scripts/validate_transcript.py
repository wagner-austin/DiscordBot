from __future__ import annotations

import argparse

from dotenv import find_dotenv, load_dotenv

from clubbot.config import load_config
from clubbot.services.transcript.app import TranscriptService


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate transcript fetching for a YouTube URL")
    parser.add_argument("url", help="YouTube video URL")
    parser.add_argument("-o", "--out", default="transcript.txt", help="Output file path")
    args = parser.parse_args()

    load_dotenv(find_dotenv(), override=True)
    cfg = load_config()
    svc = TranscriptService(cfg)

    try:
        res = svc.fetch_cleaned(args.url)
    except Exception as exc:  # pragma: no cover - manual validation tool
        print(f"Error: {exc}")
        return 1

    print(f"Fetched transcript for: {res.url}")
    print(f"Video ID: {res.video_id}")
    preview = res.text[:300].replace("\n", " ")
    print(f"Preview: {preview}...")
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(res.text)
    print(f"Saved to {args.out} ({len(res.text)} chars)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
