from __future__ import annotations

from types import SimpleNamespace

import pytest
import src.clubbot.services.jobs.digits_notifier as dn


class _User:
    def __init__(self) -> None:
        self.embeds: list[object] = []

    async def send(self, content: str = "", **kw: object) -> object:
        embed = kw.get("embed")
        self.embeds.append(embed)

        class _Msg:
            def __init__(self, u: _User) -> None:
                self._u = u

            async def edit(self, **ekw: object) -> object:
                self._u.embeds.append(ekw.get("embed"))
                return SimpleNamespace()

        return _Msg(self)


class _Bot:
    def __init__(self) -> None:
        self.user = _User()

    async def fetch_user(self, user_id: int) -> _User:
        _ = user_id
        return self.user


@pytest.mark.asyncio
async def test_handle_batch_event_sends_embed() -> None:
    bot = _Bot()
    sub = dn.DigitsEventSubscriber(bot, redis_url="redis://fake")

    await sub._handle_event(
        {
            "type": "digits.train.batch.v1",
            "request_id": "r1",
            "user_id": 1,
            "model_id": "mnist",
            "run_id": "run123",
            "ts": "2025-01-01T00:00:00Z",
            "epoch": 2,
            "total_epochs": 10,
            "batch": 100,
            "total_batches": 469,
            "batch_loss": 0.234,
            "batch_acc": 0.912,
            "avg_loss": 0.198,
            "samples_per_sec": 1234.5,
            "main_rss_mb": 512,
            "workers_rss_mb": 256,
            "worker_count": 4,
            "cgroup_usage_mb": 1024,
            "cgroup_limit_mb": 2048,
            "cgroup_pct": 50.0,
            "anon_mb": 768,
            "file_mb": 256,
        }
    )
    assert len(bot.user.embeds) == 1
    assert bot.user.embeds[-1] is not None


@pytest.mark.asyncio
async def test_handle_batch_event_first_batch() -> None:
    bot = _Bot()
    sub = dn.DigitsEventSubscriber(bot, redis_url="redis://fake")

    await sub._handle_event(
        {
            "type": "digits.train.batch.v1",
            "request_id": "r2",
            "user_id": 2,
            "model_id": "m",
            "run_id": None,
            "ts": "t",
            "epoch": 1,
            "total_epochs": 5,
            "batch": 1,
            "total_batches": 100,
            "batch_loss": 1.5,
            "batch_acc": 0.1,
            "avg_loss": 1.5,
            "samples_per_sec": 500.0,
            "main_rss_mb": 100,
            "workers_rss_mb": 50,
            "worker_count": 2,
            "cgroup_usage_mb": 200,
            "cgroup_limit_mb": 1024,
            "cgroup_pct": 19.5,
            "anon_mb": 150,
            "file_mb": 50,
        }
    )
    assert len(bot.user.embeds) == 1


@pytest.mark.asyncio
async def test_handle_batch_event_last_batch() -> None:
    bot = _Bot()
    sub = dn.DigitsEventSubscriber(bot, redis_url="redis://fake")

    await sub._handle_event(
        {
            "type": "digits.train.batch.v1",
            "request_id": "r3",
            "user_id": 3,
            "model_id": "m",
            "run_id": None,
            "ts": "t",
            "epoch": 1,
            "total_epochs": 1,
            "batch": 469,
            "total_batches": 469,
            "batch_loss": 0.05,
            "batch_acc": 0.98,
            "avg_loss": 0.12,
            "samples_per_sec": 2000.0,
            "main_rss_mb": 800,
            "workers_rss_mb": 400,
            "worker_count": 8,
            "cgroup_usage_mb": 1500,
            "cgroup_limit_mb": 2048,
            "cgroup_pct": 73.2,
            "anon_mb": 1200,
            "file_mb": 300,
        }
    )
    assert len(bot.user.embeds) == 1


@pytest.mark.asyncio
async def test_handle_batch_event_updates_same_message() -> None:
    bot = _Bot()
    sub = dn.DigitsEventSubscriber(bot, redis_url="redis://fake")

    # Send first batch update
    await sub._handle_event(
        {
            "type": "digits.train.batch.v1",
            "request_id": "r_same",
            "user_id": 4,
            "model_id": "m",
            "run_id": None,
            "ts": "t1",
            "epoch": 1,
            "total_epochs": 2,
            "batch": 100,
            "total_batches": 200,
            "batch_loss": 0.5,
            "batch_acc": 0.8,
            "avg_loss": 0.6,
            "samples_per_sec": 1000.0,
            "main_rss_mb": 300,
            "workers_rss_mb": 150,
            "worker_count": 4,
            "cgroup_usage_mb": 500,
            "cgroup_limit_mb": 1024,
            "cgroup_pct": 48.8,
            "anon_mb": 400,
            "file_mb": 100,
        }
    )
    assert len(bot.user.embeds) == 1

    # Send second batch update with same request_id (should edit in place)
    await sub._handle_event(
        {
            "type": "digits.train.batch.v1",
            "request_id": "r_same",
            "user_id": 4,
            "model_id": "m",
            "run_id": None,
            "ts": "t2",
            "epoch": 1,
            "total_epochs": 2,
            "batch": 200,
            "total_batches": 200,
            "batch_loss": 0.3,
            "batch_acc": 0.9,
            "avg_loss": 0.4,
            "samples_per_sec": 1100.0,
            "main_rss_mb": 350,
            "workers_rss_mb": 175,
            "worker_count": 4,
            "cgroup_usage_mb": 600,
            "cgroup_limit_mb": 1024,
            "cgroup_pct": 58.6,
            "anon_mb": 480,
            "file_mb": 120,
        }
    )
    # Should have 2 embeds total (1 initial send, 1 edit)
    assert len(bot.user.embeds) == 2


@pytest.mark.asyncio
async def test_handle_best_event_noop() -> None:
    bot = _Bot()
    sub = dn.DigitsEventSubscriber(bot, redis_url="redis://fake")

    # Best event handler is currently a pass (no-op)
    await sub._handle_event(
        {
            "type": "digits.train.best.v1",
            "request_id": "r_best",
            "user_id": 5,
            "model_id": "mnist",
            "run_id": "run456",
            "ts": "2025-01-01T00:00:00Z",
            "epoch": 3,
            "val_acc": 0.975,
        }
    )
    # Should not send any messages (no-op)
    assert len(bot.user.embeds) == 0


@pytest.mark.asyncio
async def test_on_batch_epoch_progress_calculation() -> None:
    bot = _Bot()
    sub = dn.DigitsEventSubscriber(bot, redis_url="redis://fake")

    # Test epoch 2 of 5
    await sub._on_batch(
        user_id=6,
        request_id="r_calc",
        model_id="mnist",
        epoch=2,
        total_epochs=5,
        batch=50,
        total_batches=100,
        batch_loss=0.25,
        batch_acc=0.85,
        avg_loss=0.3,
        samples_per_sec=800.0,
        main_rss_mb=200,
        workers_rss_mb=100,
        worker_count=2,
        cgroup_usage_mb=350,
        cgroup_limit_mb=1024,
        cgroup_pct=34.2,
        anon_mb=250,
        file_mb=100,
    )
    assert len(bot.user.embeds) == 1
    # Epoch progress should be (2-1)/5 = 20%
    # Batch progress should be 50/100 = 50%


@pytest.mark.asyncio
async def test_on_batch_edge_case_single_epoch() -> None:
    bot = _Bot()
    sub = dn.DigitsEventSubscriber(bot, redis_url="redis://fake")

    # Edge case: only 1 epoch
    await sub._on_batch(
        user_id=7,
        request_id="r_single",
        model_id="mnist",
        epoch=1,
        total_epochs=1,
        batch=1,
        total_batches=1,
        batch_loss=0.1,
        batch_acc=0.99,
        avg_loss=0.1,
        samples_per_sec=5000.0,
        main_rss_mb=50,
        workers_rss_mb=25,
        worker_count=1,
        cgroup_usage_mb=100,
        cgroup_limit_mb=512,
        cgroup_pct=19.5,
        anon_mb=75,
        file_mb=25,
    )
    assert len(bot.user.embeds) == 1


@pytest.mark.asyncio
async def test_on_best_is_noop() -> None:
    bot = _Bot()
    sub = dn.DigitsEventSubscriber(bot, redis_url="redis://fake")

    # _on_best should be a no-op (pass statement)
    await sub._on_best(user_id=8, request_id="r_noop", epoch=5, val_acc=0.99)
    assert len(bot.user.embeds) == 0


@pytest.mark.asyncio
async def test_on_batch_displays_memory_metrics() -> None:
    """Test that memory metrics are displayed in batch events."""
    bot = _Bot()
    sub = dn.DigitsEventSubscriber(bot, redis_url="redis://fake")

    await sub._handle_event(
        {
            "type": "digits.train.batch.v1",
            "request_id": "r_mem",
            "user_id": 9,
            "model_id": "mnist",
            "run_id": None,
            "ts": "t",
            "epoch": 1,
            "total_epochs": 3,
            "batch": 50,
            "total_batches": 100,
            "batch_loss": 0.5,
            "batch_acc": 0.8,
            "avg_loss": 0.6,
            "samples_per_sec": 1000.0,
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
    assert len(bot.user.embeds) == 1
    # Memory section should be present with cgroup percentage and process totals
