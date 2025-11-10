from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from .digits_events import DEFAULT_DIGITS_EVENTS_CHANNEL, EventV1, try_decode_event


@dataclass(frozen=True)
class TrainingConfig:
    """Immutable training configuration for display in progress messages."""

    model_id: str
    total_epochs: int
    queue: str
    batch_size: int | None = None
    learning_rate: float | None = None
    device: str | None = None
    cpu_cores: int | None = None
    memory_mb: int | None = None
    optimal_threads: int | None = None
    optimal_workers: int | None = None
    augment: bool | None = None
    aug_rotate: float | None = None
    aug_translate: float | None = None
    noise_prob: float | None = None
    dots_prob: float | None = None


@dataclass(frozen=True)
class BatchProgress:
    """Batch-level progress metrics for training updates."""

    epoch: int
    total_epochs: int
    batch: int
    total_batches: int
    batch_loss: float
    batch_acc: float
    avg_loss: float
    samples_per_sec: float
    main_rss_mb: int
    workers_rss_mb: int
    worker_count: int
    cgroup_usage_mb: int
    cgroup_limit_mb: int
    cgroup_pct: float
    anon_mb: int
    file_mb: int


@dataclass(frozen=True)
class TrainingMetrics:
    """Cumulative training metrics tracked throughout the lifecycle for final summary."""

    final_avg_loss: float = 0.0
    final_train_loss: float = 0.0
    total_time_s: float = 0.0
    avg_samples_per_sec: float = 0.0
    best_epoch: int = 0
    peak_memory_mb: int = 0


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
    # Store training config from StartedV1 for use in subsequent progress messages
    _configs: dict[str, TrainingConfig] = field(default_factory=dict, init=False, repr=False)
    # Track cumulative metrics throughout training for final summary
    _metrics: dict[str, TrainingMetrics] = field(default_factory=dict, init=False, repr=False)

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
            _lr = event.get("learning_rate")
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
                queue=event["queue"],
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
                learning_rate=(float(_lr) if isinstance(_lr, int | float) else None),
                augment=(_aug if isinstance(_aug, bool) else None),
                aug_rotate=(float(_ar) if isinstance(_ar, int | float) else None),
                aug_translate=(float(_at) if isinstance(_at, int | float) else None),
                noise_prob=(float(_np) if isinstance(_np, int | float) else None),
                dots_prob=(float(_dp) if isinstance(_dp, int | float) else None),
            )
            return
        if event["type"] == "digits.train.batch.v1":
            await self._on_batch(
                user_id=event["user_id"],
                request_id=event["request_id"],
                model_id=event["model_id"],
                epoch=event["epoch"],
                total_epochs=event["total_epochs"],
                batch=event["batch"],
                total_batches=event["total_batches"],
                batch_loss=event["batch_loss"],
                batch_acc=event["batch_acc"],
                avg_loss=event["avg_loss"],
                samples_per_sec=event["samples_per_sec"],
                main_rss_mb=event["main_rss_mb"],
                workers_rss_mb=event["workers_rss_mb"],
                worker_count=event["worker_count"],
                cgroup_usage_mb=event["cgroup_usage_mb"],
                cgroup_limit_mb=event["cgroup_limit_mb"],
                cgroup_pct=event["cgroup_pct"],
                anon_mb=event["anon_mb"],
                file_mb=event["file_mb"],
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
        if event["type"] == "digits.train.best.v1":
            await self._on_best(
                user_id=event["user_id"],
                request_id=event["request_id"],
                epoch=event["epoch"],
                val_acc=event["val_acc"],
            )
            return
        if event["type"] == "digits.train.artifact.v1":
            await self._on_artifact(
                user_id=event["user_id"],
                request_id=event["request_id"],
                path=event["path"],
            )
            return
        if event["type"] == "digits.train.upload.v1":
            await self._on_upload(
                user_id=event["user_id"],
                request_id=event["request_id"],
                status=event["status"],
                model_bytes=event["model_bytes"],
                manifest_bytes=event["manifest_bytes"],
            )
            return
        if event["type"] == "digits.train.prune.v1":
            await self._on_prune(
                user_id=event["user_id"],
                request_id=event["request_id"],
                deleted_count=event["deleted_count"],
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
                queue=event["queue"],
                status=event["status"],
            )

    def _build_training_embed(  # noqa: C901
        self,
        *,
        request_id: str,
        config: TrainingConfig,
        status: str,
        progress: BatchProgress | None = None,
        final_val_acc: float | None = None,
        final_metrics: TrainingMetrics | None = None,
        run_id: str | None = None,
        error_kind: str | None = None,
        error_message: str | None = None,
    ) -> discord.Embed:
        """Build a consistent training status embed that updates based on event type."""
        # Title and color based on status
        title_icons = {
            "starting": "🚀",
            "training": "⚡",
            "completed": "✅",
            "failed": "❌",
            "canceled": "🚫",
        }
        colors = {
            "starting": 0x5865F2,  # Blurple
            "training": 0x5865F2,  # Blurple
            "completed": 0x57F287,  # Green
            "failed": 0xED4245,  # Red
            "canceled": 0xFAA61A,  # Orange
        }
        icon = title_icons.get(status, "📊")
        color = colors.get(status, 0x5865F2)
        title = f"{icon} Training {status.title()}"

        embed = discord.Embed(
            title=title,
            description=f"Training **{config.model_id}**",
            color=color,
        )

        # Always show configuration
        config_lines = [f"**Epochs:** `{config.total_epochs}`"]
        if isinstance(config.batch_size, int):
            config_lines.append(f"**Batch Size:** `{config.batch_size}`")
        if isinstance(config.device, str) and config.device:
            config_lines.append(f"**Device:** `{config.device}`")
        if isinstance(config.learning_rate, float):
            config_lines.append(f"**Learning Rate:** `{config.learning_rate}`")
        embed.add_field(name="⚙️ Configuration", value="\n".join(config_lines), inline=True)

        # Always show resources
        resource_lines = []
        if isinstance(config.cpu_cores, int):
            resource_lines.append(f"**CPU Cores:** `{config.cpu_cores}`")
        if isinstance(config.memory_mb, int):
            resource_lines.append(f"**Memory:** `{config.memory_mb} MB`")
        if isinstance(config.optimal_threads, int):
            resource_lines.append(f"**Threads:** `{config.optimal_threads}`")
        if isinstance(config.optimal_workers, int):
            resource_lines.append(f"**Workers:** `{config.optimal_workers}`")
        if resource_lines:
            embed.add_field(name="💻 Resources", value="\n".join(resource_lines), inline=True)

        # Always show augmentations
        if config.augment:
            aug_lines = []
            if isinstance(config.aug_rotate, float) and config.aug_rotate > 0:
                aug_lines.append(f"🔄 **Rotation:** `±{config.aug_rotate}°`")
            if isinstance(config.aug_translate, float) and config.aug_translate > 0:
                aug_lines.append(f"↔️ **Translation:** `±{config.aug_translate * 100:.0f}%`")
            if isinstance(config.noise_prob, float) and config.noise_prob > 0:
                aug_lines.append(f"⚡ **Noise:** `{config.noise_prob * 100:.0f}%`")
            if isinstance(config.dots_prob, float) and config.dots_prob > 0:
                aug_lines.append(f"🔴 **Dots:** `{config.dots_prob * 100:.0f}%`")
            if aug_lines:
                embed.add_field(name="✨ Augmentations", value="\n".join(aug_lines), inline=False)
        else:
            embed.add_field(name="✨ Augmentations", value="*None*", inline=False)

        # Show progress bars and metrics during training
        if progress:
            epoch_pct = ((progress.epoch - 1) / max(1, config.total_epochs)) * 100
            batch_pct = (progress.batch / max(1, progress.total_batches)) * 100
            epoch_filled = max(
                0, min(20, int(((progress.epoch - 1) / max(1, config.total_epochs)) * 20))
            )
            epoch_bar = "█" * epoch_filled + "░" * (20 - epoch_filled)
            batch_filled = max(
                0, min(20, int((progress.batch / max(1, progress.total_batches)) * 20))
            )
            batch_bar = "█" * batch_filled + "░" * (20 - batch_filled)

            progress_text = (
                f"**Epoch {progress.epoch}/{config.total_epochs}** ({epoch_pct:.0f}%)\n"
                f"`{epoch_bar}`\n\n"
                f"**Batch {progress.batch}/{progress.total_batches}** ({batch_pct:.0f}%)\n"
                f"`{batch_bar}`"
            )
            embed.add_field(name="📈 Progress", value=progress_text, inline=False)

            batch_metrics = [
                f"**Batch Loss:** `{progress.batch_loss:.4f}`",
                f"**Batch Accuracy:** `{progress.batch_acc:.2%}`",
            ]
            embed.add_field(name="📊 Current Batch", value="\n".join(batch_metrics), inline=True)

            overall_metrics = [
                f"**Average Loss:** `{progress.avg_loss:.4f}`",
                f"**Speed:** `{progress.samples_per_sec:.1f} samples/sec`",
            ]
            embed.add_field(name="📈 Overall", value="\n".join(overall_metrics), inline=True)

            total_process_mb = progress.main_rss_mb + progress.workers_rss_mb
            memory_metrics = [
                f"**Memory:** `{progress.cgroup_pct:.1f}%` ({progress.cgroup_usage_mb}/{progress.cgroup_limit_mb} MB)",  # noqa: E501
                f"**Process:** `{total_process_mb} MB` (main: {progress.main_rss_mb}, workers: {progress.workers_rss_mb})",  # noqa: E501
            ]
            embed.add_field(name="💾 Memory", value="\n".join(memory_metrics), inline=False)

        # Show training summary and final performance on completion
        if status == "completed":
            if isinstance(final_metrics, TrainingMetrics):
                summary_lines = []
                if final_metrics.final_avg_loss > 0:
                    val = f"{final_metrics.final_avg_loss:.4f}"
                    summary_lines.append(f"**Final Avg Loss:** `{val}`")
                if final_metrics.final_train_loss > 0:
                    val = f"{final_metrics.final_train_loss:.4f}"
                    summary_lines.append(f"**Final Train Loss:** `{val}`")
                if final_metrics.total_time_s > 0:
                    total_mins = int(final_metrics.total_time_s // 60)
                    total_secs = int(final_metrics.total_time_s % 60)
                    time_str = (
                        f"{total_mins}m {total_secs}s" if total_mins > 0 else f"{total_secs}s"
                    )
                    summary_lines.append(f"**Total Time:** `{time_str}`")
                if final_metrics.avg_samples_per_sec > 0:
                    speed = f"{final_metrics.avg_samples_per_sec:.1f}"
                    summary_lines.append(f"**Avg Speed:** `{speed} samples/sec`")
                if final_metrics.best_epoch > 0:
                    summary_lines.append(f"**Best Epoch:** `{final_metrics.best_epoch}`")
                if final_metrics.peak_memory_mb > 0:
                    mb = final_metrics.peak_memory_mb
                    summary_lines.append(f"**Peak Memory:** `{mb} MB`")
                if summary_lines:
                    summary_value = "\n".join(summary_lines)
                    embed.add_field(name="📊 Training Summary", value=summary_value, inline=False)

            if isinstance(final_val_acc, float):
                embed.add_field(
                    name="🎯 Final Performance",
                    value=f"**Best Validation Accuracy:** `{final_val_acc:.2%}`",
                    inline=False,
                )
            if isinstance(run_id, str) and run_id:
                embed.add_field(name="🕐 Run ID", value=f"`{run_id}`", inline=True)

        # Show error details on failure
        if status in ("failed", "canceled") and isinstance(error_message, str):
            if error_kind == "user":
                embed.add_field(
                    name="⚠️ Configuration Issue",
                    value=f"```{error_message}```",
                    inline=False,
                )
                embed.add_field(
                    name="💡 Next Steps",
                    value="Please check your configuration and try again.",
                    inline=False,
                )
            else:
                embed.add_field(
                    name="⚠️ System Error",
                    value=f"```{error_message}```",
                    inline=False,
                )
                if "memory" in error_message.lower() or "oom" in error_message.lower():
                    next_steps = (
                        "**Memory Issue Detected:**\n"
                        "• Reduce batch size in your training config\n"
                        "• Reduce DataLoader workers\n"
                        "• Try training with fewer epochs to conserve resources"
                    )
                elif "upload" in error_message.lower() or "artifact" in error_message.lower():
                    next_steps = (
                        "**Artifact Upload Failed:**\n"
                        "The model trained successfully but couldn't be saved. "
                        "Check worker logs and try again."
                    )
                else:
                    next_steps = (
                        "Please try again. If the issue persists, "
                        "check worker logs or contact support."
                    )
                embed.add_field(name="💡 Next Steps", value=next_steps, inline=False)

        # Always show job info with queue and status
        job_info_lines = [f"**Queue:** `{config.queue}`", f"**Status:** `{status}`"]
        embed.add_field(name="📋 Job Info", value="\n".join(job_info_lines), inline=False)

        embed.set_footer(text=f"Request ID: {request_id}")
        return embed

    async def _on_started(
        self,
        *,
        user_id: int,
        request_id: str,
        model_id: str,
        total_epochs: int,
        queue: str,
        cpu_cores: int | None = None,
        optimal_threads: int | None = None,
        memory_mb: int | None = None,
        optimal_workers: int | None = None,
        max_batch_size: int | None = None,
        device: str | None = None,
        batch_size: int | None = None,
        learning_rate: float | None = None,
        augment: bool | None = None,
        aug_rotate: float | None = None,
        aug_translate: float | None = None,
        noise_prob: float | None = None,
        dots_prob: float | None = None,
    ) -> None:
        # Store training config for use in subsequent progress messages
        config = TrainingConfig(
            model_id=model_id,
            total_epochs=total_epochs,
            queue=queue,
            batch_size=batch_size,
            learning_rate=learning_rate,
            device=device,
            cpu_cores=cpu_cores,
            memory_mb=memory_mb,
            optimal_threads=optimal_threads,
            optimal_workers=optimal_workers,
            augment=augment,
            aug_rotate=aug_rotate,
            aug_translate=aug_translate,
            noise_prob=noise_prob,
            dots_prob=dots_prob,
        )
        self._configs[request_id] = config

        # Initialize metrics tracking for this training session
        self._metrics[request_id] = TrainingMetrics()

        # Build and send initial status message
        embed = self._build_training_embed(request_id=request_id, config=config, status="starting")
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
        # Update cumulative metrics
        current_metrics = self._metrics.get(request_id, TrainingMetrics())
        final_train_loss = (
            train_loss if isinstance(train_loss, float) else current_metrics.final_train_loss
        )
        total_time = current_metrics.total_time_s + (time_s if isinstance(time_s, float) else 0.0)
        self._metrics[request_id] = TrainingMetrics(
            final_avg_loss=current_metrics.final_avg_loss,
            final_train_loss=final_train_loss,
            total_time_s=total_time,
            avg_samples_per_sec=current_metrics.avg_samples_per_sec,
            best_epoch=current_metrics.best_epoch,
            peak_memory_mb=current_metrics.peak_memory_mb,
        )

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

    async def _on_batch(
        self,
        *,
        user_id: int,
        request_id: str,
        model_id: str,
        epoch: int,
        total_epochs: int,
        batch: int,
        total_batches: int,
        batch_loss: float,
        batch_acc: float,
        avg_loss: float,
        samples_per_sec: float,
        main_rss_mb: int,
        workers_rss_mb: int,
        worker_count: int,
        cgroup_usage_mb: int,
        cgroup_limit_mb: int,
        cgroup_pct: float,
        anon_mb: int,
        file_mb: int,
    ) -> None:
        # Retrieve stored config, or create minimal config if not found
        config = self._configs.get(request_id)
        if not config:
            # Create minimal config (happens when batch event arrives before started event in tests)
            config = TrainingConfig(model_id=model_id, total_epochs=total_epochs, queue="digits")
            self._configs[request_id] = config

        # Update cumulative metrics
        current_metrics = self._metrics.get(request_id, TrainingMetrics())
        total_process_mb = main_rss_mb + workers_rss_mb
        self._metrics[request_id] = TrainingMetrics(
            final_avg_loss=avg_loss,
            final_train_loss=current_metrics.final_train_loss,
            total_time_s=current_metrics.total_time_s,
            avg_samples_per_sec=samples_per_sec,
            best_epoch=current_metrics.best_epoch,
            peak_memory_mb=max(current_metrics.peak_memory_mb, total_process_mb),
        )

        # Build batch progress metrics
        progress = BatchProgress(
            epoch=epoch,
            total_epochs=total_epochs,
            batch=batch,
            total_batches=total_batches,
            batch_loss=batch_loss,
            batch_acc=batch_acc,
            avg_loss=avg_loss,
            samples_per_sec=samples_per_sec,
            main_rss_mb=main_rss_mb,
            workers_rss_mb=workers_rss_mb,
            worker_count=worker_count,
            cgroup_usage_mb=cgroup_usage_mb,
            cgroup_limit_mb=cgroup_limit_mb,
            cgroup_pct=cgroup_pct,
            anon_mb=anon_mb,
            file_mb=file_mb,
        )

        # Build and update message with training status
        embed = self._build_training_embed(
            request_id=request_id, config=config, status="training", progress=progress
        )
        await self._notify(user_id, request_id, embed)

    async def _on_best(self, *, user_id: int, request_id: str, epoch: int, val_acc: float) -> None:
        # Update metrics to track which epoch produced the best model
        current_metrics = self._metrics.get(request_id, TrainingMetrics())
        self._metrics[request_id] = TrainingMetrics(
            final_avg_loss=current_metrics.final_avg_loss,
            final_train_loss=current_metrics.final_train_loss,
            total_time_s=current_metrics.total_time_s,
            avg_samples_per_sec=current_metrics.avg_samples_per_sec,
            best_epoch=epoch,
            peak_memory_mb=current_metrics.peak_memory_mb,
        )
        # Suppress unused parameter warnings
        _ = (user_id, val_acc)

    async def _on_artifact(self, *, user_id: int, request_id: str, path: str) -> None:
        # Lightweight notification that artifact was created locally
        # No need to update the message for this internal step
        _ = (user_id, request_id, path)
        pass

    async def _on_upload(
        self,
        *,
        user_id: int,
        request_id: str,
        status: int,
        model_bytes: int,
        manifest_bytes: int,
    ) -> None:
        # Lightweight notification about upload status
        # Could optionally update message if status != 200
        _ = (user_id, request_id, status, model_bytes, manifest_bytes)
        pass

    async def _on_prune(self, *, user_id: int, request_id: str, deleted_count: int) -> None:
        # Lightweight notification about cleanup
        # No need to update the message for this internal step
        _ = (user_id, request_id, deleted_count)
        pass

    async def _on_completed(
        self, *, user_id: int, request_id: str, model_id: str, run_id: str, val_acc: float
    ) -> None:
        # Retrieve stored config for context
        config = self._configs.get(request_id)
        if not config:
            # No config stored, can't build complete message
            return

        # Retrieve stored metrics for final summary
        metrics = self._metrics.get(request_id)

        # Build and update message with completed status
        embed = self._build_training_embed(
            request_id=request_id,
            config=config,
            status="completed",
            final_val_acc=val_acc,
            final_metrics=metrics,
            run_id=run_id,
        )
        await self._notify(user_id, request_id, embed)

        # Clean up stored config and metrics
        self._configs.pop(request_id, None)
        self._metrics.pop(request_id, None)

    async def _on_failed(
        self,
        *,
        user_id: int,
        request_id: str,
        model_id: str,
        error_kind: str,
        message: str,
        queue: str,
        status: str,
    ) -> None:
        # Retrieve stored config for context - use it if available, otherwise create minimal config
        config = self._configs.get(request_id)
        if not config:
            # No config stored - create minimal config from event data for consistent display
            config = TrainingConfig(
                model_id=model_id,
                total_epochs=0,  # Unknown
                queue=queue,
            )

        # Build and update message with failed/canceled status
        embed = self._build_training_embed(
            request_id=request_id,
            config=config,
            status=status,  # "failed" or "canceled"
            error_kind=error_kind,
            error_message=message,
        )
        await self._notify(user_id, request_id, embed)

        # Clean up stored config and metrics
        self._configs.pop(request_id, None)
        self._metrics.pop(request_id, None)

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
