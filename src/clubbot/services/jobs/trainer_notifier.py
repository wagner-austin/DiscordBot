from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

import discord
from discord.ext import commands

from .trainer_events import DEFAULT_TRAINER_EVENTS_CHANNEL, Event, try_decode_event


class _MessageProto(Protocol):  # pragma: no cover - typing only
    async def edit(self, *args: object, **kwargs: object) -> object: ...


class _UserProto(Protocol):  # pragma: no cover - typing only
    async def send(self, *args: object, **kwargs: object) -> _MessageProto: ...


class _BotProto(Protocol):  # pragma: no cover - typing only
    async def fetch_user(self, user_id: int) -> _UserProto: ...


BotType = _BotProto | commands.Bot


class _PubSubProto(Protocol):  # pragma: no cover - typing only
    async def subscribe(self, *channels: str) -> None: ...

    async def get_message(
        self,
        ignore_subscribe_messages: bool = True,
        timeout: float = 1.0,
    ) -> dict[str, object] | None: ...

    async def close(self) -> None: ...


class _RedisAsyncProto(Protocol):  # pragma: no cover - typing only
    async def get(self, name: str) -> str | None: ...

    def pubsub(self) -> _PubSubProto: ...


if TYPE_CHECKING:

    def _redis_from_url(url: str) -> _RedisAsyncProto: ...
else:  # pragma: no cover - runtime import only

    def _redis_from_url(url: str):
        import redis.asyncio as redis_asyncio

        return redis_asyncio.from_url(url, encoding="utf-8", decode_responses=True)

    BotType = commands.Bot


def _make_logger() -> logging.Logger:
    return logging.getLogger(__name__)


@dataclass
class TrainerEventSubscriber:
    bot: BotType
    redis_url: str
    events_channel: str = DEFAULT_TRAINER_EVENTS_CHANNEL
    _task: asyncio.Task[None] | None = field(default=None, init=False, repr=False)
    _logger: logging.Logger = field(default_factory=_make_logger, init=False, repr=False)
    # Always send a fresh message per update to simplify typing and UX
    # (avoid in-place edit to keep code strictly typed)
    _messages: dict[str, object] = field(default_factory=dict, init=False, repr=False)

    def start(self) -> None:
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._run(), name="trainer-event-subscriber")

    async def stop(self) -> None:
        task = self._task
        if task is None:
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        self._task = None

    async def _run(self) -> None:  # pragma: no cover - integration path
        conn = _redis_from_url(self.redis_url)
        pubsub = conn.pubsub()
        await pubsub.subscribe(self.events_channel)
        try:
            while True:
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if not msg:
                    await asyncio.sleep(0.05)
                    continue
                data = msg.get("data")
                if not isinstance(data, str):
                    continue
                ev = try_decode_event(data)
                if ev is None:
                    continue
                try:
                    await self._handle_event(ev)
                except (RuntimeError, ValueError, TypeError, KeyError) as e:
                    self._logger.debug("Trainer subscriber handling error: %s", e)
        finally:
            with contextlib.suppress(Exception):
                await pubsub.close()

    async def _notify(self, user_id: int, request_id: str, embed: discord.Embed) -> None:
        bot = self.bot
        try:
            user = await bot.fetch_user(user_id)
            await user.send(embed=embed)
        except (
            discord.Forbidden,
            discord.HTTPException,
            discord.NotFound,
        ) as e:  # pragma: no cover - DM delivery/environmental
            self._logger.debug("DM delivery failed user=%s req=%s err=%s", user_id, request_id, e)

    async def _handle_event(self, ev: Event) -> None:
        if ev["type"] == "trainer.train.started.v1":
            embed = discord.Embed(
                title="Training Started",
                description=(
                    f"Model `{ev['model_family']}` size `{ev['model_size']}`\n"
                    f"Total epochs: `{ev['total_epochs']}`\nQueue: `{ev['queue']}`"
                ),
                color=0x5865F2,
            )
            await self._notify(ev["user_id"], ev["request_id"], embed)
            return
        if ev["type"] == "trainer.train.progress.v1":
            pct = (ev["epoch"] / max(1, ev["total_epochs"])) * 100.0
            embed2 = discord.Embed(
                title="Training Progress",
                description=(
                    f"Epoch `{ev['epoch']}/{ev['total_epochs']}` ({pct:.1f}%)\n"
                    f"Loss: `{ev['loss']:.4f}`"
                ),
                color=0xFEE75C,
            )
            await self._notify(ev["user_id"], ev["request_id"], embed2)
            return
        if ev["type"] == "trainer.train.completed.v1":
            embed3 = discord.Embed(
                title="Training Completed",
                description=(
                    f"Loss: `{ev['loss']:.4f}`, Perplexity: `{ev['perplexity']:.2f}`\n"
                    f"Artifact: `{ev['artifact_path']}`"
                ),
                color=0x57F287,
            )
            await self._notify(ev["user_id"], ev["request_id"], embed3)
            return
        if ev["type"] == "trainer.train.failed.v1":
            embed4 = discord.Embed(
                title="Training Failed",
                description=f"{ev['error_kind'].title()}: {ev['message']}",
                color=0xED4245,
            )
            await self._notify(ev["user_id"], ev["request_id"], embed4)
            return
