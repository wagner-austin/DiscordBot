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
        self.user = _OkUser()

    async def fetch_user(self, user_id: int) -> _OkUser:
        return self.user


class _FailBot:
    async def fetch_user(self, user_id: int):
        raise RuntimeError("nope")


@pytest.mark.asyncio
async def test_notify_user_success_and_failure_are_safe() -> None:
    cog = BaseCog()
    # Success path
    ok_bot = _OkBot()
    cog.bot = ok_bot
    await cog.notify_user(1, "hello")
    assert ok_bot.user.messages == ["hello"]

    # Failure path: should not raise
    fail_bot = _FailBot()
    cog.bot = fail_bot
    await cog.notify_user(2, "ignored")
