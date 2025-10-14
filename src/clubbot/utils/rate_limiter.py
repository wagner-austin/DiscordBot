from __future__ import annotations

import time


class RateLimiter:
    """Simple per-user, per-command in-memory rate limiter (1-minute window)."""

    def __init__(self, per_minute: int) -> None:
        self.per_minute = per_minute
        self._events: dict[tuple[int, str], list[float]] = {}

    def allow(self, user_id: int, command: str) -> tuple[bool, float]:
        now = time.time()
        key = (user_id, command)
        arr = self._events.setdefault(key, [])
        # Prune old timestamps (>60s)
        cutoff = now - 60
        arr[:] = [t for t in arr if t > cutoff]
        if len(arr) >= self.per_minute:
            # Next available seconds
            next_ok = 60 - (now - arr[0])
            return False, max(1.0, next_ok)
        arr.append(now)
        return True, 0.0
