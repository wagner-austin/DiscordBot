from __future__ import annotations

from collections.abc import Iterable

class Retry:
    def __init__(self, max: int, interval: Iterable[int]) -> None: ...
