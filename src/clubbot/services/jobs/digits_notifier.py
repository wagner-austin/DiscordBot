from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from .digits_events import (
    DEFAULT_DIGITS_EVENTS_CHANNEL,
    DigitsTrainCompletedEvent,
    DigitsTrainFailedEvent,
    DigitsTrainProgressEvent,
    DigitsTrainStartedEvent,
    try_decode_event,
)

if TYPE_CHECKING:  # narrow async redis interface for typing
    from typing import Protocol

    class _UserProto(Protocol):  # pragma: no cover - typing only
        async def send(self, *args: object, **kwargs: object) -> object: ...

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

    def _redis_from_url(url: str) -> _RedisAsyncProto: ...
else:  # pragma: no cover - runtime import only

    def _redis_from_url(url: str):
        import redis.asyncio as redis_asyncio

        return redis_asyncio.from_url(url, encoding="utf-8", decode_responses=True)

    BotType = commands.Bot


Event = (
    DigitsTrainStartedEvent
    | DigitsTrainProgressEvent
    | DigitsTrainCompletedEvent
    | DigitsTrainFailedEvent
)


def _make_logger() -> logging.Logger:
    return logging.getLogger(__name__)


@dataclass
class DigitsEventSubscriber:
    bot: BotType
    redis_url: str
    events_channel: str = DEFAULT_DIGITS_EVENTS_CHANNEL
    _task: asyncio.Task[None] | None = field(default=None, init=False, repr=False)
    _logger: logging.Logger = field(default_factory=_make_logger, init=False, repr=False)

    def start(self) -> None:
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._run(), name="digits-event-subscriber")

    async def stop(self) -> None:
        task = self._task
        if task is None:
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        self._task = None

    async def _run(self) -> None:  # pragma: no cover - exercised indirectly in integration
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
                event = try_decode_event(data)
                if event is None:
                    continue
                try:
                    await self._handle_event(event)
                except (RuntimeError, ValueError, TypeError, KeyError) as e:
                    self._logger.debug("Digits subscriber handling error: %s", e)
        finally:
            with contextlib.suppress(Exception):
                await pubsub.close()

    async def _handle_event(self, event: Event) -> None:
        if event["type"] == "started":
            await self._on_started(
                user_id=event["user_id"],
                request_id=event["request_id"],
                model_id=event["model_id"],
                total_epochs=event["total_epochs"],
            )
            return
        if event["type"] == "progress":
            await self._on_progress(
                user_id=event["user_id"],
                request_id=event["request_id"],
                epoch=event["epoch"],
                total_epochs=event["total_epochs"],
                val_acc=event.get("val_acc"),
            )
            return
        if event["type"] == "completed":
            await self._on_completed(
                user_id=event["user_id"],
                request_id=event["request_id"],
                model_id=event["model_id"],
                run_id=event["run_id"],
                val_acc=event["val_acc"],
            )
            return
        await self._on_failed(
            user_id=event["user_id"],
            request_id=event["request_id"],
            model_id=event["model_id"],
            error_kind=event["error_kind"],
            message=event["message"],
        )

    async def _on_started(
        self, *, user_id: int, request_id: str, model_id: str, total_epochs: int
    ) -> None:
        msg = (
            f"Training started for model '{model_id}' "
            f"(req={request_id}, epochs={total_epochs})."
        )
        await self._notify(user_id, msg)

    async def _on_progress(
        self, *, user_id: int, request_id: str, epoch: int, total_epochs: int, val_acc: float | None
    ) -> None:
        tail = f" val_acc={val_acc:.4f}" if isinstance(val_acc, float) else ""
        msg = f"Training progress (req={request_id}): epoch {epoch}/{total_epochs}." + tail
        await self._notify(user_id, msg)

    async def _on_completed(
        self, *, user_id: int, request_id: str, model_id: str, run_id: str, val_acc: float
    ) -> None:
        await self._notify(
            user_id,
            (
                f"Training completed for model '{model_id}' (req={request_id}). "
                f"best_val_acc={val_acc:.4f} run_id={run_id}"
            ),
        )

    async def _on_failed(
        self, *, user_id: int, request_id: str, model_id: str, error_kind: str, message: str
    ) -> None:
        if error_kind == "user":
            await self._notify(user_id, f"Training failed: {message} (req={request_id}).")
            return
        await self._notify(
            user_id,
            (f"An error occurred during training (req={request_id}). " f"Please try again later."),
        )

    async def _notify(self, user_id: int, message: str) -> None:
        try:
            user = await self.bot.fetch_user(user_id)
            await user.send(message)
        except (discord.HTTPException, discord.Forbidden, discord.NotFound):
            self._logger.debug("Failed to DM user=%s", user_id)
