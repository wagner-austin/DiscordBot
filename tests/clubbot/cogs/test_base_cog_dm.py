from __future__ import annotations

import pytest
from src.clubbot.cogs.base import BaseCog


class _OkUser:
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def send(self, content: str, **_: object) -> None:
        self.messages.append(content)


class _OkBot:
    def __init__(self) -> None:
        self._u = _OkUser()

    async def fetch_user(self, user_id: int) -> _OkUser:
        return self._u


class _FailBot:
    async def fetch_user(self, user_id: int) -> object:
        raise RuntimeError("nope")


@pytest.mark.asyncio
async def test_notify_user_success_and_failure_are_safe() -> None:
    cog = BaseCog()
    # Success path
    ok_bot = _OkBot()
    cog.bot = ok_bot
    await cog.notify_user(1, "hello")
    assert ok_bot._u.messages == ["hello"]

    # Failure path: should not raise
    fail_bot = _FailBot()
    cog.bot = fail_bot
    await cog.notify_user(2, "ignored")
