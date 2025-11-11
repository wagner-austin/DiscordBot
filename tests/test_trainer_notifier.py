from __future__ import annotations

import asyncio

import discord

from clubbot.services.jobs.trainer_notifier import TrainerEventSubscriber


class _FakeMsg:
    async def edit(self, *args, **kwargs):  # pragma: no cover - not used in this path
        return None


class _FakeUser:
    def __init__(self) -> None:
        self.sent: list[discord.Embed] = []

    async def send(self, *, embed: discord.Embed) -> _FakeMsg:
        self.sent.append(embed)
        return _FakeMsg()


class _FakeBot:
    def __init__(self) -> None:
        self._user = _FakeUser()
        self.last_user_id: int | None = None

    async def fetch_user(self, user_id: int) -> _FakeUser:
        self.last_user_id = user_id
        return self._user


def _started() -> dict[str, object]:
    return {
        "type": "trainer.train.started.v1",
        "request_id": "r",
        "run_id": "run",
        "user_id": 1,
        "model_family": "gpt2",
        "model_size": "small",
        "total_epochs": 1,
        "queue": "training",
    }


def _progress() -> dict[str, object]:
    return {
        "type": "trainer.train.progress.v1",
        "request_id": "r",
        "run_id": "run",
        "user_id": 1,
        "epoch": 1,
        "total_epochs": 1,
        "step": 10,
        "loss": 1.0,
    }


def _completed() -> dict[str, object]:
    return {
        "type": "trainer.train.completed.v1",
        "request_id": "r",
        "run_id": "run",
        "user_id": 1,
        "loss": 0.5,
        "perplexity": 2.0,
        "artifact_path": "/x",
    }


def _failed() -> dict[str, object]:
    return {
        "type": "trainer.train.failed.v1",
        "request_id": "r",
        "run_id": "run",
        "user_id": 1,
        "error_kind": "system",
        "message": "boom",
        "status": "failed",
    }


def test_notifier_handles_all_events() -> None:
    bot = _FakeBot()
    sub = TrainerEventSubscriber(bot=bot, redis_url="redis://example")

    async def _run() -> None:
        await sub._handle_event(_started())
        await sub._handle_event(_progress())
        await sub._handle_event(_completed())
        await sub._handle_event(_failed())

    asyncio.get_event_loop().run_until_complete(_run())
    assert bot.last_user_id == 1
    assert isinstance(bot._user.sent[0], discord.Embed)
