from __future__ import annotations

import time


class RateLimiter:
    """Simple per-user, per-command in-memory rate limiter.

    - Tracks timestamps in a sliding window of ``window_seconds`` (default 60)
    - Allows up to ``per_window`` events within that window
    """

    def __init__(self, per_window: int, window_seconds: int = 60) -> None:
        self.per_window = per_window
        self.window_seconds = window_seconds
        self._events: dict[tuple[int, str], list[float]] = {}

    def allow(self, user_id: int, command: str) -> tuple[bool, float]:
        now = time.time()
        key = (user_id, command)
        arr = self._events.setdefault(key, [])
        cutoff = now - self.window_seconds
        arr[:] = [t for t in arr if t > cutoff]
        if len(arr) >= self.per_window:
            # Next available seconds
            next_ok = self.window_seconds - (now - arr[0])
            return False, max(0.1, next_ok)
        arr.append(now)
        return True, 0.0
