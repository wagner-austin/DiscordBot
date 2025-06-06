"""
tests.helpers
-------------
Centralised utility functions and fixtures for the test-suite.
Add new helpers here instead of sprinkling them across ad-hoc files.
"""

__all__: list[str] = []


import asyncio
from contextlib import asynccontextmanager
from typing import Tuple, Any, Dict, AsyncGenerator

from bot_core.storage import acquire

# ------------------------------------------------------------------ #
# Async sleep scaler ------------------------------------------------ #
# ------------------------------------------------------------------ #


@asynccontextmanager
async def override_async_sleep(
    monkeypatch: Any, *, scale: float = 0.01
) -> AsyncGenerator[None, None]:
    """
    Temporarily monkey-patch ``asyncio.sleep`` so that real sleeps
    are divided by *scale*.  Handy for speeding up slow background
    tasks in tests.
    """
    original_sleep = asyncio.sleep

    async def fast_sleep(seconds: float) -> None:
        return await original_sleep(seconds * scale)

    monkeypatch.setattr(asyncio, "sleep", fast_sleep)
    try:
        yield
    finally:
        monkeypatch.setattr(asyncio, "sleep", original_sleep)


# ------------------------------------------------------------------ #
# Simple DB helpers ------------------------------------------------- #
# ------------------------------------------------------------------ #


async def insert_record(query: str, params: Tuple[Any, ...]) -> int:
    async with acquire() as conn:
        cursor = await conn.execute(query, params)
        lastrowid = cursor.lastrowid
        if lastrowid is None:
            raise ValueError("Expected DB insert to return an int id, got None")
        return int(lastrowid)


async def fetch_one(query: str, params: Tuple[Any, ...] = ()) -> Dict[str, Any] | None:
    async with acquire() as conn:
        cursor = await conn.execute(query, params)
        row = await cursor.fetchone()
        if row is None:
            return None
        return dict(row)


async def cleanup_table(table_name: str) -> None:
    async with acquire() as conn:
        await conn.execute(f"DELETE FROM {table_name}")
        await conn.commit()
