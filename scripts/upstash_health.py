from __future__ import annotations

import os
import sys

import httpx


def main() -> int:
    url = (os.getenv("UPSTASH_REDIS_REST_URL") or "").strip().rstrip("/")
    tok = (os.getenv("UPSTASH_REDIS_REST_TOKEN") or "").strip()
    if not url or not tok:
        print("Missing UPSTASH_REDIS_REST_URL or UPSTASH_REDIS_REST_TOKEN", file=sys.stderr)
        return 2
    try:
        with httpx.Client(timeout=10.0) as c:
            # Try pipeline first
            r = c.post(
                f"{url}/pipeline",
                headers={"Authorization": f"Bearer {tok}"},
                json={"commands": [["SET", "health:flag", "ok"], ["GET", "health:flag"]]},
            )
            print(f"pipeline_status={r.status_code}")
            print(f"pipeline_body={r.text}")
            if 200 <= r.status_code < 300:
                return 0
            # Try command endpoints
            r1 = c.post(f"{url}/lpush/health:queue/ok", headers={"Authorization": f"Bearer {tok}"})
            r2 = c.get(f"{url}/rpop/health:queue", headers={"Authorization": f"Bearer {tok}"})
            print(f"lpush_status={r1.status_code}")
            print(f"lpush_body={r1.text}")
            print(f"rpop_status={r2.status_code}")
            print(f"rpop_body={r2.text}")
            ok = 200 <= r1.status_code < 300 and 200 <= r2.status_code < 300
            return 0 if ok else 1
    except Exception as e:
        print(f"error={e}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
