from __future__ import annotations

import asyncio

import discord

from clubbot.services.jobs.trainer_notifier import TrainerEventSubscriber


def test_notifier_notify_dm_failure_logs() -> None:
    class _Resp:
        def __init__(self) -> None:
            self.status = 403
            self.reason = "Forbidden"

    class _User:
        async def send(self, *, embed: discord.Embed):
            # Provide a response-like object with required attributes
            raise discord.Forbidden(_Resp(), "no")

    class _Bot:
        async def fetch_user(self, user_id: int):
            return _User()

    sub = TrainerEventSubscriber(bot=_Bot(), redis_url="redis://example")

    async def _run() -> None:
        await sub._notify(1, "r", discord.Embed(title="t"))

    asyncio.get_event_loop().run_until_complete(_run())


def test_notifier_unknown_event_is_noop() -> None:
    class _Bot:
        async def fetch_user(self, user_id: int):  # pragma: no cover - not used
            return None

    sub = TrainerEventSubscriber(bot=_Bot(), redis_url="redis://example")

    async def _run() -> None:
        await sub._handle_event({"type": "trainer.train.unknown"})

    asyncio.get_event_loop().run_until_complete(_run())
