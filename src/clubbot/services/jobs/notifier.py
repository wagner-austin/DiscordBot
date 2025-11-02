from __future__ import annotations

import asyncio
import contextlib
import io
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from .events import (
    DEFAULT_EVENTS_CHANNEL,
    TranscriptCompletedEvent,
    TranscriptFailedEvent,
    try_decode_event,
)

if TYPE_CHECKING:  # narrow async redis interface for typing

    class _RedisAsyncProto:  # pragma: no cover - typing only
        async def get(self, name: str) -> str | None: ...

        class _PubSub:
            async def subscribe(self, *channels: str) -> None: ...

            async def get_message(
                self,
                ignore_subscribe_messages: bool = True,
                timeout: float = 1.0,
            ) -> dict[str, object] | None: ...

            async def close(self) -> None: ...

        def pubsub(self) -> _PubSub: ...

    def _redis_from_url(url: str) -> _RedisAsyncProto: ...
else:  # pragma: no cover - runtime import only

    def _redis_from_url(url: str):
        import redis.asyncio as redis_asyncio

        return redis_asyncio.from_url(url, encoding="utf-8", decode_responses=True)


def _too_large(limit_mb: int, data: bytes) -> bool:
    return limit_mb > 0 and len(data) > (limit_mb * 1024 * 1024)


def _make_logger() -> logging.Logger:
    return logging.getLogger(__name__)


Event = TranscriptCompletedEvent | TranscriptFailedEvent


@dataclass
class TranscriptEventSubscriber:
    bot: commands.Bot
    redis_url: str
    events_channel: str = DEFAULT_EVENTS_CHANNEL
    max_attachment_mb: int = 25
    _task: asyncio.Task[None] | None = field(default=None, init=False, repr=False)
    _logger: logging.Logger = field(default_factory=_make_logger, init=False, repr=False)

    def start(self) -> None:
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._run(), name="transcript-event-subscriber")

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
                    await self._handle_event(conn, event)
                except (RuntimeError, ValueError, TypeError, KeyError) as e:
                    self._logger.debug("Subscriber handling error: %s", e)
        finally:
            with contextlib.suppress(Exception):
                await pubsub.close()

    async def _handle_event(self, conn: _RedisAsyncProto, event: Event) -> None:
        # Narrow type of redis conn using TYPE_CHECKING protocol in practice
        if event["type"] == "completed":
            await self._on_completed(conn, event)
            return
        await self._on_failed(event)

    async def _on_completed(self, conn: _RedisAsyncProto, e: TranscriptCompletedEvent) -> None:
        # Fetch transcript text by key and DM file; fallback if too large
        text = await conn.get(e["content_key"])
        if not isinstance(text, str):
            # Key expired or missing; notify user of completion with pointer
            await self._notify(e["user_id"], f"Your transcript is ready (req={e['request_id']}).")
            return
        data = text.encode("utf-8")
        if _too_large(self.max_attachment_mb, data):
            await self._notify(
                e["user_id"],
                (
                    f"Transcript is too large to attach (> {self.max_attachment_mb} MB) "
                    f"(req={e['request_id']}). Please try a shorter video."
                ),
            )
            return
        header = f"Transcript for <{e['url']}> (req={e['request_id']})"
        file = discord.File(fp=io.BytesIO(data), filename=f"transcript_{e['video_id']}.txt")
        await self._dm_file(e["user_id"], header, file)

    async def _on_failed(self, e: TranscriptFailedEvent) -> None:
        if e["error_kind"] == "user":
            await self._notify(
                e["user_id"],
                f"Transcription failed: {e['message']} (req={e['request_id']})",
            )
            return
        await self._notify(
            e["user_id"],
            (
                f"An error occurred processing your transcription (req={e['request_id']}). "
                f"Please try again later."
            ),
        )

    async def _notify(self, user_id: int, message: str) -> None:
        try:
            user = await self.bot.fetch_user(user_id)
            await user.send(message)
        except (discord.HTTPException, discord.Forbidden, discord.NotFound):
            self._logger.debug("Failed to DM user=%s", user_id)

    async def _dm_file(self, user_id: int, content: str, file: discord.File) -> None:
        try:
            user = await self.bot.fetch_user(user_id)
            await user.send(content, file=file)
        except (discord.HTTPException, discord.Forbidden, discord.NotFound):
            self._logger.debug("Failed to DM file to user=%s", user_id)
