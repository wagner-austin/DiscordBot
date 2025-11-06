from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from .digits_events import DEFAULT_DIGITS_EVENTS_CHANNEL, EventV1, try_decode_event

if TYPE_CHECKING:  # narrow async redis interface for typing
    from typing import Protocol

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

    def _redis_from_url(url: str) -> _RedisAsyncProto: ...
else:  # pragma: no cover - runtime import only

    def _redis_from_url(url: str):
        import redis.asyncio as redis_asyncio

        return redis_asyncio.from_url(url, encoding="utf-8", decode_responses=True)

    BotType = commands.Bot


Event = EventV1


def _make_logger() -> logging.Logger:
    return logging.getLogger(__name__)


@dataclass
class DigitsEventSubscriber:
    bot: BotType
    redis_url: str
    events_channel: str = DEFAULT_DIGITS_EVENTS_CHANNEL
    _task: asyncio.Task[None] | None = field(default=None, init=False, repr=False)
    _logger: logging.Logger = field(default_factory=_make_logger, init=False, repr=False)
    # Track one DM message per training request for in-place updates
    _messages: dict[str, object] = field(default_factory=dict, init=False, repr=False)

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
        if event["type"] == "digits.train.started.v1":
            # Narrow optional config types for mypy via local binding + isinstance guards
            _bs = event.get("batch_size")
            _aug = event.get("augment")
            _ar = event.get("aug_rotate")
            _at = event.get("aug_translate")
            _np = event.get("noise_prob")
            _dp = event.get("dots_prob")

            await self._on_started(
                user_id=event["user_id"],
                request_id=event["request_id"],
                model_id=event["model_id"],
                total_epochs=event["total_epochs"],
                cpu_cores=(
                    event.get("cpu_cores") if isinstance(event.get("cpu_cores"), int) else None
                ),
                optimal_threads=(
                    event.get("optimal_threads")
                    if isinstance(event.get("optimal_threads"), int)
                    else None
                ),
                memory_mb=(
                    event.get("memory_mb") if isinstance(event.get("memory_mb"), int) else None
                ),
                optimal_workers=(
                    event.get("optimal_workers")
                    if isinstance(event.get("optimal_workers"), int)
                    else None
                ),
                max_batch_size=(
                    event.get("max_batch_size")
                    if isinstance(event.get("max_batch_size"), int)
                    else None
                ),
                device=(event.get("device") if isinstance(event.get("device"), str) else None),
                batch_size=(_bs if isinstance(_bs, int) else None),
                augment=(_aug if isinstance(_aug, bool) else None),
                aug_rotate=(float(_ar) if isinstance(_ar, int | float) else None),
                aug_translate=(float(_at) if isinstance(_at, int | float) else None),
                noise_prob=(float(_np) if isinstance(_np, int | float) else None),
                dots_prob=(float(_dp) if isinstance(_dp, int | float) else None),
            )
            return
        if event["type"] == "digits.train.epoch.v1":
            await self._on_progress(
                user_id=event["user_id"],
                request_id=event["request_id"],
                epoch=event["epoch"],
                total_epochs=event["total_epochs"],
                val_acc=event.get("val_acc"),
                train_loss=event.get("train_loss"),
                time_s=event.get("time_s"),
            )
            return
        if event["type"] == "digits.train.completed.v1":
            await self._on_completed(
                user_id=event["user_id"],
                request_id=event["request_id"],
                model_id=event["model_id"],
                run_id=(event["run_id"] or ""),
                val_acc=event["val_acc"],
            )
            return
        if event["type"] == "digits.train.failed.v1":
            await self._on_failed(
                user_id=event["user_id"],
                request_id=event["request_id"],
                model_id=event["model_id"],
                error_kind=event["error_kind"],
                message=event["message"],
            )

    async def _on_started(  # noqa: C901
        self,
        *,
        user_id: int,
        request_id: str,
        model_id: str,
        total_epochs: int,
        cpu_cores: int | None = None,
        optimal_threads: int | None = None,
        memory_mb: int | None = None,
        optimal_workers: int | None = None,
        max_batch_size: int | None = None,
        device: str | None = None,
        batch_size: int | None = None,
        augment: bool | None = None,
        aug_rotate: float | None = None,
        aug_translate: float | None = None,
        noise_prob: float | None = None,
        dots_prob: float | None = None,
    ) -> None:
        # Create a beautiful embed with fields
        embed = discord.Embed(
            title="🚀 Training Started",
            description=f"Training session initiated for **{model_id}**",
            color=0x5865F2,  # Blurple
        )

        # Training Configuration
        config_lines = [f"**Epochs:** `{total_epochs}`"]
        if isinstance(batch_size, int):
            config_lines.append(f"**Batch Size:** `{batch_size}`")
        if isinstance(device, str) and device:
            config_lines.append(f"**Device:** `{device}`")
        embed.add_field(name="⚙️ Configuration", value="\n".join(config_lines), inline=True)

        # Resource Allocation
        resource_lines = []
        if isinstance(cpu_cores, int):
            resource_lines.append(f"**CPU Cores:** `{cpu_cores}`")
        if isinstance(memory_mb, int):
            resource_lines.append(f"**Memory:** `{memory_mb} MB`")
        if isinstance(optimal_threads, int):
            resource_lines.append(f"**Threads:** `{optimal_threads}`")
        if isinstance(optimal_workers, int):
            resource_lines.append(f"**Workers:** `{optimal_workers}`")
        if resource_lines:
            embed.add_field(name="💻 Resources", value="\n".join(resource_lines), inline=True)

        # Augmentations
        if augment:
            aug_lines = []
            if isinstance(aug_rotate, float) and aug_rotate > 0:
                aug_lines.append(f"🔄 Rotation: `±{aug_rotate}°`")
            if isinstance(aug_translate, float) and aug_translate > 0:
                aug_lines.append(f"↔️ Translation: `±{aug_translate * 100:.0f}%`")
            if isinstance(noise_prob, float) and noise_prob > 0:
                aug_lines.append(f"⚡ Noise: `{noise_prob * 100:.0f}%`")
            if isinstance(dots_prob, float) and dots_prob > 0:
                aug_lines.append(f"🔴 Dots: `{dots_prob * 100:.0f}%`")
            if aug_lines:
                embed.add_field(name="✨ Augmentations", value="\n".join(aug_lines), inline=False)
        else:
            embed.add_field(name="✨ Augmentations", value="*None*", inline=False)

        embed.set_footer(text=f"Request ID: {request_id}")
        await self._notify(user_id, request_id, embed)

    async def _on_progress(
        self,
        *,
        user_id: int,
        request_id: str,
        epoch: int,
        total_epochs: int,
        val_acc: float | None,
        train_loss: float | None = None,
        time_s: float | None = None,
    ) -> None:
        # Beautiful progress bar with 20 slots for smoother visualization
        progress_pct = (epoch / max(1, total_epochs)) * 100
        filled = max(0, min(20, int((epoch / max(1, total_epochs)) * 20)))
        bar = "█" * filled + "░" * (20 - filled)

        embed = discord.Embed(
            title="⚡ Training Progress",
            description=f"**Epoch {epoch} of {total_epochs}** ({progress_pct:.1f}%)\n`{bar}`",
            color=0xFEE75C,  # Yellow
        )

        # Metrics
        metrics_lines = []
        if isinstance(val_acc, float):
            metrics_lines.append(f"**Validation Accuracy:** `{val_acc:.2%}`")
        if isinstance(train_loss, float):
            metrics_lines.append(f"**Training Loss:** `{train_loss:.4f}`")
        if metrics_lines:
            embed.add_field(name="📊 Metrics", value="\n".join(metrics_lines), inline=True)

        # Timing
        if isinstance(time_s, float):
            mins = int(time_s // 60)
            secs = int(time_s % 60)
            time_str = f"{mins}m {secs}s" if mins > 0 else f"{secs}s"
            embed.add_field(name="⏱️ Epoch Time", value=f"`{time_str}`", inline=True)

        embed.set_footer(text=f"Request ID: {request_id}")
        await self._notify(user_id, request_id, embed)

    async def _on_completed(
        self, *, user_id: int, request_id: str, model_id: str, run_id: str, val_acc: float
    ) -> None:
        embed = discord.Embed(
            title="✅ Training Completed Successfully!",
            description=f"Training finished for **{model_id}**",
            color=0x57F287,  # Green
        )

        embed.add_field(
            name="🎯 Final Performance",
            value=f"**Best Validation Accuracy:** `{val_acc:.2%}`",
            inline=False,
        )

        embed.add_field(name="🔖 Model ID", value=f"`{model_id}`", inline=True)
        embed.add_field(name="🕐 Run ID", value=f"`{run_id}`", inline=True)

        embed.set_footer(text=f"Request ID: {request_id}")
        await self._notify(user_id, request_id, embed)

    async def _on_failed(
        self, *, user_id: int, request_id: str, model_id: str, error_kind: str, message: str
    ) -> None:
        if error_kind == "user":
            text = f"Training failed: {message}"
        else:
            text = "An error occurred during training. Please try again later."
        embed = discord.Embed(
            title="🟥 Training Failed",
            description=f"{text}\nRequest: `{request_id}`\nModel: `{model_id}`",
            color=0xE74C3C,
        )
        await self._notify(user_id, request_id, embed)

    async def _notify(self, user_id: int, request_id: str, embed: discord.Embed) -> None:
        try:
            user = await self.bot.fetch_user(user_id)
            existing = self._messages.get(request_id)
            if existing is not None and hasattr(existing, "edit"):
                # Edit in place
                await existing.edit(embed=embed)
                return
            # Otherwise, send a new DM and store it for future updates
            msg = await user.send(embed=embed)
            self._messages[request_id] = msg
        except (discord.HTTPException, discord.Forbidden, discord.NotFound):
            self._logger.debug("Failed to DM user=%s", user_id)
