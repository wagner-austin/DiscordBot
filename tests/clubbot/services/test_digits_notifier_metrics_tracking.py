from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import discord
import pytest
import src.clubbot.services.jobs.digits_notifier as dn


class _User:
    def __init__(self) -> None:
        self.embeds: list[discord.Embed] = []

    async def send(self, content: str = "", **kw: object) -> object:
        embed = kw.get("embed")
        if isinstance(embed, discord.Embed):
            self.embeds.append(embed)

        class _Msg:
            def __init__(self, u: _User) -> None:
                self._u = u

            async def edit(self, **ekw: object) -> object:
                emb = ekw.get("embed")
                if isinstance(emb, discord.Embed):
                    self._u.embeds.append(emb)
                return SimpleNamespace()

        return _Msg(self)


class _Bot:
    def __init__(self) -> None:
        self.user = _User()

    async def fetch_user(self, user_id: int) -> _User:
        _ = user_id
        return self.user


def _get_field(embed: discord.Embed, name: str) -> dict[str, Any] | None:
    """Helper to get a field by name from an embed."""
    for field in embed.fields:
        if field.name == name:
            return {"name": field.name, "value": field.value, "inline": field.inline}
    return None


def _has_field(embed: discord.Embed, name: str) -> bool:
    """Helper to check if an embed has a field with the given name."""
    return _get_field(embed, name) is not None


@pytest.mark.asyncio
async def test_metrics_tracked_throughout_lifecycle() -> None:
    """Test that metrics are tracked from start to finish and displayed in completion."""
    bot = _Bot()
    sub = dn.DigitsEventSubscriber(bot, redis_url="redis://fake")

    # Start training
    await sub._handle_event(
        {
            "type": "digits.train.started.v1",
            "request_id": "req_metrics",
            "user_id": 100,
            "model_id": "mnist_full",
            "run_id": "run_2025",
            "ts": "2025-01-01T00:00:00Z",
            "total_epochs": 5,
            "queue": "default",
            "batch_size": 64,
            "learning_rate": 0.001,
            "device": "cpu",
        }
    )

    # Send batch events
    await sub._handle_event(
        {
            "type": "digits.train.batch.v1",
            "request_id": "req_metrics",
            "user_id": 100,
            "model_id": "mnist_full",
            "run_id": "run_2025",
            "ts": "2025-01-01T00:01:00Z",
            "epoch": 1,
            "total_epochs": 5,
            "batch": 100,
            "total_batches": 200,
            "batch_loss": 0.5,
            "batch_acc": 0.8,
            "avg_loss": 0.6,
            "samples_per_sec": 1234.5,
            "main_rss_mb": 400,
            "workers_rss_mb": 200,
            "worker_count": 4,
            "cgroup_usage_mb": 700,
            "cgroup_limit_mb": 1024,
            "cgroup_pct": 68.4,
            "anon_mb": 500,
            "file_mb": 200,
        }
    )

    # Send epoch progress
    await sub._handle_event(
        {
            "type": "digits.train.epoch.v1",
            "request_id": "req_metrics",
            "user_id": 100,
            "model_id": "mnist_full",
            "run_id": "run_2025",
            "ts": "2025-01-01T00:02:00Z",
            "epoch": 1,
            "total_epochs": 5,
            "train_loss": 0.45,
            "val_acc": 0.85,
            "time_s": 120.5,
        }
    )

    # Send best model event
    await sub._handle_event(
        {
            "type": "digits.train.best.v1",
            "request_id": "req_metrics",
            "user_id": 100,
            "model_id": "mnist_full",
            "run_id": "run_2025",
            "ts": "2025-01-01T00:02:30Z",
            "epoch": 1,
            "val_acc": 0.85,
        }
    )

    # Complete training
    await sub._handle_event(
        {
            "type": "digits.train.completed.v1",
            "request_id": "req_metrics",
            "user_id": 100,
            "model_id": "mnist_full",
            "run_id": "run_2025",
            "ts": "2025-01-01T00:10:00Z",
            "val_acc": 0.92,
        }
    )

    # Get the final completion embed
    # Should have 4 embeds: started, batch, epoch, completed (best doesn't send embed)
    assert len(bot.user.embeds) == 4
    final_embed = bot.user.embeds[-1]

    # Deep inspection of the completion embed
    assert isinstance(final_embed, discord.Embed)
    assert final_embed.title == "✅ Training Completed"
    assert final_embed.color is not None
    assert final_embed.color.value == 0x57F287  # Green
    assert "mnist_full" in (final_embed.description or "")

    # Check that Training Summary field exists
    assert _has_field(final_embed, "📊 Training Summary")
    summary_field = _get_field(final_embed, "📊 Training Summary")
    assert summary_field is not None
    summary_value = summary_field["value"]

    # Verify metrics are present in the summary
    assert "Final Avg Loss" in summary_value
    assert "0.6000" in summary_value  # avg_loss from batch
    assert "Final Train Loss" in summary_value
    assert "0.4500" in summary_value  # train_loss from epoch
    assert "Total Time" in summary_value
    assert "2m 0s" in summary_value  # 120.5 seconds
    assert "Avg Speed" in summary_value
    assert "1234.5 samples/sec" in summary_value
    assert "Best Epoch" in summary_value
    assert "1" in summary_value  # best epoch
    assert "Peak Memory" in summary_value
    assert "600 MB" in summary_value  # 400 + 200

    # Check Final Performance field
    assert _has_field(final_embed, "🎯 Final Performance")
    perf_field = _get_field(final_embed, "🎯 Final Performance")
    assert perf_field is not None
    assert "92.00%" in perf_field["value"] or "0.92" in perf_field["value"]

    # Check Run ID field
    assert _has_field(final_embed, "🕐 Run ID")
    run_id_field = _get_field(final_embed, "🕐 Run ID")
    assert run_id_field is not None
    assert "run_2025" in run_id_field["value"]

    # Check footer
    assert final_embed.footer.text == "Request ID: req_metrics"


@pytest.mark.asyncio
async def test_completion_without_metrics_shows_empty_summary() -> None:
    """Test that completion without prior events doesn't break."""
    bot = _Bot()
    sub = dn.DigitsEventSubscriber(bot, redis_url="redis://fake")

    # Complete training without any prior events (edge case)
    await sub._on_completed(
        user_id=101,
        request_id="req_no_metrics",
        model_id="mnist_no_prior",
        run_id="run_orphan",
        val_acc=0.88,
    )

    # Should not send embed because no config exists
    assert len(bot.user.embeds) == 0


@pytest.mark.asyncio
async def test_completion_with_partial_metrics() -> None:
    """Test completion with only some metrics tracked."""
    bot = _Bot()
    sub = dn.DigitsEventSubscriber(bot, redis_url="redis://fake")

    # Start training
    await sub._handle_event(
        {
            "type": "digits.train.started.v1",
            "request_id": "req_partial",
            "user_id": 102,
            "model_id": "mnist_partial",
            "run_id": None,
            "ts": "2025-01-01T00:00:00Z",
            "total_epochs": 2,
            "queue": "default",
        }
    )

    # Send only best event (no batch or epoch)
    await sub._handle_event(
        {
            "type": "digits.train.best.v1",
            "request_id": "req_partial",
            "user_id": 102,
            "model_id": "mnist_partial",
            "run_id": None,
            "ts": "2025-01-01T00:01:00Z",
            "epoch": 2,
            "val_acc": 0.95,
        }
    )

    # Complete
    await sub._handle_event(
        {
            "type": "digits.train.completed.v1",
            "request_id": "req_partial",
            "user_id": 102,
            "model_id": "mnist_partial",
            "run_id": "partial_run",
            "ts": "2025-01-01T00:05:00Z",
            "val_acc": 0.95,
        }
    )

    final_embed = bot.user.embeds[-1]
    assert isinstance(final_embed, discord.Embed)

    # Training Summary should exist but only show best_epoch
    summary_field = _get_field(final_embed, "📊 Training Summary")
    if summary_field:
        summary_value = summary_field["value"]
        # Should have best epoch
        assert "Best Epoch" in summary_value
        assert "2" in summary_value
        # Should NOT have avg loss, train loss, time, speed, or memory (all zero)
        assert "Final Avg Loss" not in summary_value
        assert "Final Train Loss" not in summary_value
        assert "Total Time" not in summary_value
        assert "Avg Speed" not in summary_value
        assert "Peak Memory" not in summary_value


@pytest.mark.asyncio
async def test_batch_updates_metrics_correctly() -> None:
    """Test that batch events correctly update metrics."""
    bot = _Bot()
    sub = dn.DigitsEventSubscriber(bot, redis_url="redis://fake")

    # Start training
    await sub._handle_event(
        {
            "type": "digits.train.started.v1",
            "request_id": "req_batch_metrics",
            "user_id": 103,
            "model_id": "m",
            "run_id": None,
            "ts": "t",
            "total_epochs": 1,
            "queue": "default",
        }
    )

    # Send first batch - low memory
    await sub._handle_event(
        {
            "type": "digits.train.batch.v1",
            "request_id": "req_batch_metrics",
            "user_id": 103,
            "model_id": "m",
            "run_id": None,
            "ts": "t",
            "epoch": 1,
            "total_epochs": 1,
            "batch": 1,
            "total_batches": 3,
            "batch_loss": 1.0,
            "batch_acc": 0.5,
            "avg_loss": 1.0,
            "samples_per_sec": 100.0,
            "main_rss_mb": 100,
            "workers_rss_mb": 50,
            "worker_count": 2,
            "cgroup_usage_mb": 200,
            "cgroup_limit_mb": 1024,
            "cgroup_pct": 20.0,
            "anon_mb": 150,
            "file_mb": 50,
        }
    )

    # Send second batch - higher memory (should update peak)
    await sub._handle_event(
        {
            "type": "digits.train.batch.v1",
            "request_id": "req_batch_metrics",
            "user_id": 103,
            "model_id": "m",
            "run_id": None,
            "ts": "t",
            "epoch": 1,
            "total_epochs": 1,
            "batch": 2,
            "total_batches": 3,
            "batch_loss": 0.5,
            "batch_acc": 0.8,
            "avg_loss": 0.75,
            "samples_per_sec": 200.0,
            "main_rss_mb": 300,
            "workers_rss_mb": 200,
            "worker_count": 2,
            "cgroup_usage_mb": 600,
            "cgroup_limit_mb": 1024,
            "cgroup_pct": 58.6,
            "anon_mb": 500,
            "file_mb": 100,
        }
    )

    # Send third batch - lower memory again
    await sub._handle_event(
        {
            "type": "digits.train.batch.v1",
            "request_id": "req_batch_metrics",
            "user_id": 103,
            "model_id": "m",
            "run_id": None,
            "ts": "t",
            "epoch": 1,
            "total_epochs": 1,
            "batch": 3,
            "total_batches": 3,
            "batch_loss": 0.3,
            "batch_acc": 0.9,
            "avg_loss": 0.6,
            "samples_per_sec": 150.0,
            "main_rss_mb": 150,
            "workers_rss_mb": 100,
            "worker_count": 2,
            "cgroup_usage_mb": 300,
            "cgroup_limit_mb": 1024,
            "cgroup_pct": 29.3,
            "anon_mb": 250,
            "file_mb": 50,
        }
    )

    # Complete
    await sub._handle_event(
        {
            "type": "digits.train.completed.v1",
            "request_id": "req_batch_metrics",
            "user_id": 103,
            "model_id": "m",
            "run_id": "batch_run",
            "ts": "t",
            "val_acc": 0.90,
        }
    )

    final_embed = bot.user.embeds[-1]
    summary_field = _get_field(final_embed, "📊 Training Summary")
    assert summary_field is not None
    summary_value = summary_field["value"]

    # Should show final avg_loss (from last batch)
    assert "0.6000" in summary_value
    # Should show final samples_per_sec (from last batch)
    assert "150.0 samples/sec" in summary_value
    # Should show peak memory (from second batch: 300 + 200 = 500)
    assert "500 MB" in summary_value


@pytest.mark.asyncio
async def test_epoch_events_accumulate_time() -> None:
    """Test that epoch events accumulate total training time."""
    bot = _Bot()
    sub = dn.DigitsEventSubscriber(bot, redis_url="redis://fake")

    # Start training
    await sub._handle_event(
        {
            "type": "digits.train.started.v1",
            "request_id": "req_time",
            "user_id": 104,
            "model_id": "m",
            "run_id": None,
            "ts": "t",
            "total_epochs": 3,
            "queue": "default",
        }
    )

    # Epoch 1: 60 seconds
    await sub._handle_event(
        {
            "type": "digits.train.epoch.v1",
            "request_id": "req_time",
            "user_id": 104,
            "model_id": "m",
            "run_id": None,
            "ts": "t",
            "epoch": 1,
            "total_epochs": 3,
            "train_loss": 0.8,
            "val_acc": 0.7,
            "time_s": 60.0,
        }
    )

    # Epoch 2: 75 seconds
    await sub._handle_event(
        {
            "type": "digits.train.epoch.v1",
            "request_id": "req_time",
            "user_id": 104,
            "model_id": "m",
            "run_id": None,
            "ts": "t",
            "epoch": 2,
            "total_epochs": 3,
            "train_loss": 0.5,
            "val_acc": 0.85,
            "time_s": 75.0,
        }
    )

    # Epoch 3: 90 seconds
    await sub._handle_event(
        {
            "type": "digits.train.epoch.v1",
            "request_id": "req_time",
            "user_id": 104,
            "model_id": "m",
            "run_id": None,
            "ts": "t",
            "epoch": 3,
            "total_epochs": 3,
            "train_loss": 0.3,
            "val_acc": 0.92,
            "time_s": 90.0,
        }
    )

    # Complete
    await sub._handle_event(
        {
            "type": "digits.train.completed.v1",
            "request_id": "req_time",
            "user_id": 104,
            "model_id": "m",
            "run_id": "time_run",
            "ts": "t",
            "val_acc": 0.92,
        }
    )

    final_embed = bot.user.embeds[-1]
    summary_field = _get_field(final_embed, "📊 Training Summary")
    assert summary_field is not None
    summary_value = summary_field["value"]

    # Total time should be 60 + 75 + 90 = 225 seconds = 3m 45s
    assert "Total Time" in summary_value
    assert "3m 45s" in summary_value
    # Final train loss should be from last epoch
    assert "0.3000" in summary_value


@pytest.mark.asyncio
async def test_failed_training_cleans_up_metrics() -> None:
    """Test that failed training cleans up metrics properly."""
    bot = _Bot()
    sub = dn.DigitsEventSubscriber(bot, redis_url="redis://fake")

    # Start training
    await sub._handle_event(
        {
            "type": "digits.train.started.v1",
            "request_id": "req_fail",
            "user_id": 105,
            "model_id": "m",
            "run_id": None,
            "ts": "t",
            "total_epochs": 5,
            "queue": "default",
        }
    )

    # Verify metrics were initialized
    assert "req_fail" in sub._metrics

    # Fail training
    await sub._handle_event(
        {
            "type": "digits.train.failed.v1",
            "request_id": "req_fail",
            "user_id": 105,
            "model_id": "m",
            "run_id": None,
            "ts": "t",
            "error_kind": "system",
            "message": "Out of memory",
            "queue": "default",
            "status": "failed",
        }
    )

    # Verify metrics were cleaned up
    assert "req_fail" not in sub._metrics
    assert "req_fail" not in sub._configs

    # Verify failure embed was sent (not checking for Training Summary)
    final_embed = bot.user.embeds[-1]
    assert isinstance(final_embed, discord.Embed)
    assert final_embed.title == "❌ Training Failed"
    assert _has_field(final_embed, "⚠️ System Error")


@pytest.mark.asyncio
async def test_completion_without_final_val_acc() -> None:
    """Test completion where final_val_acc is None (edge case)."""
    bot = _Bot()
    sub = dn.DigitsEventSubscriber(bot, redis_url="redis://fake")

    # Manually set up config and metrics without going through started event
    sub._configs["req_no_acc"] = dn.TrainingConfig(model_id="m", total_epochs=1, queue="default")
    sub._metrics["req_no_acc"] = dn.TrainingMetrics(best_epoch=1)

    # Call _on_completed directly with None for val_acc (shouldn't happen but test the branch)
    embed = sub._build_training_embed(
        request_id="req_no_acc",
        config=sub._configs["req_no_acc"],
        status="completed",
        final_val_acc=None,  # No validation accuracy
        final_metrics=sub._metrics["req_no_acc"],
        run_id=None,
    )

    # Should not have Final Performance field
    assert not _has_field(embed, "🎯 Final Performance")
    # Should have Training Summary with best_epoch
    assert _has_field(embed, "📊 Training Summary")


@pytest.mark.asyncio
async def test_completion_with_empty_run_id() -> None:
    """Test completion where run_id is empty string."""
    bot = _Bot()
    sub = dn.DigitsEventSubscriber(bot, redis_url="redis://fake")

    sub._configs["req_empty_run"] = dn.TrainingConfig(model_id="m", total_epochs=1, queue="default")

    embed = sub._build_training_embed(
        request_id="req_empty_run",
        config=sub._configs["req_empty_run"],
        status="completed",
        final_val_acc=0.9,
        final_metrics=None,
        run_id="",  # Empty run_id
    )

    # Should not have Run ID field (empty string fails isinstance check)
    assert not _has_field(embed, "🕐 Run ID")


@pytest.mark.asyncio
async def test_completion_with_all_zero_metrics() -> None:
    """Test completion with metrics but all values are zero (summary_lines empty)."""
    bot = _Bot()
    sub = dn.DigitsEventSubscriber(bot, redis_url="redis://fake")

    sub._configs["req_zero"] = dn.TrainingConfig(model_id="m", total_epochs=1, queue="default")

    # All zeros
    zero_metrics = dn.TrainingMetrics()

    embed = sub._build_training_embed(
        request_id="req_zero",
        config=sub._configs["req_zero"],
        status="completed",
        final_val_acc=0.9,
        final_metrics=zero_metrics,
        run_id="run123",
    )

    # Should NOT have Training Summary (all metrics are zero)
    assert not _has_field(embed, "📊 Training Summary")
    # Should still have Final Performance
    assert _has_field(embed, "🎯 Final Performance")
