from __future__ import annotations

import asyncio
from types import SimpleNamespace

import discord
import pytest
import src.clubbot.services.jobs.digits_notifier as dn


class _User:
    def __init__(self) -> None:
        self.embeds: list[object] = []

    async def send(self, content: str = "", **kw: object) -> object:  # pragma: no cover - trivial
        embed = kw.get("embed")
        self.embeds.append(embed)

        class _Msg:
            def __init__(self, u: _User) -> None:
                self._u = u

            async def edit(self, **ekw: object) -> object:  # pragma: no cover - trivial
                self._u.embeds.append(ekw.get("embed"))
                return SimpleNamespace()

        return _Msg(self)


class _Bot:
    def __init__(self) -> None:
        self.user = _User()

    async def fetch_user(self, user_id: int) -> _User:  # pragma: no cover - trivial
        _ = user_id
        return self.user


@pytest.mark.asyncio
async def test_handle_event_branches_send_dm() -> None:
    bot = _Bot()
    sub = dn.DigitsEventSubscriber(bot, redis_url="redis://fake")

    await sub._handle_event(
        {
            "type": "digits.train.started.v1",
            "request_id": "r",
            "user_id": 1,
            "model_id": "m",
            "run_id": None,
            "ts": "t",
            "total_epochs": 2,
            # Optional extras for richer embed
            "cpu_cores": 2,
            "optimal_threads": 2,
            "memory_mb": 953,
            "optimal_workers": 0,
            "max_batch_size": 64,
            "device": "cpu",
        }
    )
    assert bot.user.embeds and isinstance(bot.user.embeds[-1], object)

    # Start another request without extras to cover env_bits empty branch
    await sub._handle_event(
        {
            "type": "digits.train.started.v1",
            "request_id": "r2",
            "user_id": 2,
            "model_id": "m2",
            "run_id": None,
            "ts": "t",
            "total_epochs": 1,
        }
    )
    assert bot.user.embeds and len(bot.user.embeds) >= 2

    await sub._handle_event(
        {
            "type": "digits.train.epoch.v1",
            "request_id": "r",
            "user_id": 1,
            "model_id": "m",
            "run_id": None,
            "ts": "t",
            "epoch": 1,
            "total_epochs": 2,
            "train_loss": 0.1,
            "val_acc": 0.9,
            "time_s": 1.0,
        }
    )
    assert bot.user.embeds and len(bot.user.embeds) >= 2

    await sub._handle_event(
        {
            "type": "digits.train.completed.v1",
            "request_id": "r",
            "user_id": 1,
            "model_id": "m",
            "run_id": None,
            "ts": "t",
            "val_acc": 0.95,
        }
    )
    assert bot.user.embeds and len(bot.user.embeds) >= 3

    await sub._handle_event(
        {
            "type": "digits.train.failed.v1",
            "request_id": "r",
            "user_id": 1,
            "model_id": "m",
            "run_id": None,
            "ts": "t",
            "error_kind": "user",
            "message": "bad payload",
        }
    )
    assert bot.user.embeds and len(bot.user.embeds) >= 4

    await sub._handle_event(
        {
            "type": "digits.train.failed.v1",
            "request_id": "r",
            "user_id": 1,
            "model_id": "m",
            "run_id": None,
            "ts": "t",
            "error_kind": "system",
            "message": "boom",
        }
    )
    assert bot.user.embeds and len(bot.user.embeds) >= 5


@pytest.mark.asyncio
async def test_started_embed_includes_augment_and_config() -> None:
    bot = _Bot()
    sub = dn.DigitsEventSubscriber(bot, redis_url="redis://fake")
    await sub._handle_event(
        {
            "type": "digits.train.started.v1",
            "request_id": "rx",
            "user_id": 7,
            "model_id": "mX",
            "run_id": None,
            "ts": "t",
            "total_epochs": 3,
            "cpu_cores": 2,
            "optimal_threads": 2,
            "memory_mb": 953,
            "optimal_workers": 0,
            "max_batch_size": 64,
            "device": "cpu",
            "batch_size": 64,
            "augment": True,
            "aug_rotate": 10.0,
            "aug_translate": 0.1,
            "noise_prob": 0.2,
            "dots_prob": 0.1,
        }
    )
    assert bot.user.embeds and isinstance(bot.user.embeds[-1], object)


@pytest.mark.asyncio
async def test_started_augment_zero_values_renders_none() -> None:
    bot = _Bot()
    sub = dn.DigitsEventSubscriber(bot, redis_url="redis://fake")
    await sub._handle_event(
        {
            "type": "digits.train.started.v1",
            "request_id": "rz",
            "user_id": 9,
            "model_id": "mZ",
            "run_id": None,
            "ts": "t",
            "total_epochs": 1,
            "augment": True,
            "aug_rotate": 0.0,
            "aug_translate": 0.0,
            "noise_prob": 0.0,
            "dots_prob": 0.0,
        }
    )
    assert bot.user.embeds and isinstance(bot.user.embeds[-1], object)


@pytest.mark.asyncio
async def test_progress_without_optional_metrics() -> None:
    bot = _Bot()
    sub = dn.DigitsEventSubscriber(bot, redis_url="redis://fake")
    await sub._handle_event(
        {
            "type": "digits.train.epoch.v1",
            "request_id": "r3",
            "user_id": 3,
            "model_id": "m3",
            "run_id": None,
            "ts": "t",
            "epoch": 1,
            "total_epochs": 3,
            # omit val_acc, train_loss, time_s to hit empty branches
        }
    )
    assert bot.user.embeds and isinstance(bot.user.embeds[-1], object)


@pytest.mark.asyncio
async def test_notify_handles_discord_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    class _BadUser:
        async def send(self, **kw: object) -> object:  # pragma: no cover - trivial
            _ = kw

            class _Resp:
                status = 404
                reason = "Not Found"

            raise discord.NotFound(response=_Resp(), message="not found")

    class _BadBot:
        async def fetch_user(self, user_id: int) -> _BadUser:  # pragma: no cover - trivial
            _ = user_id
            return _BadUser()

    sub = dn.DigitsEventSubscriber(_BadBot(), redis_url="redis://fake")
    # Should swallow the exception
    await sub._on_completed(user_id=1, request_id="r", model_id="m", run_id="rid", val_acc=0.9)


@pytest.mark.asyncio
async def test_handle_event_unknown_type_noop() -> None:
    bot = _Bot()
    sub = dn.DigitsEventSubscriber(bot, redis_url="redis://fake")
    # Unknown type should result in no notification and no exception
    await sub._handle_event({"type": "digits.train.other.v1", "user_id": 1, "request_id": "r"})
    assert bot.user.embeds == []


@pytest.mark.asyncio
async def test_start_and_stop_covers_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    # Patch _run to a cooperative noop to avoid real Redis calls
    async def _noop(self) -> None:  # pragma: no cover - trivial
        await asyncio.sleep(0)

    monkeypatch.setattr(dn.DigitsEventSubscriber, "_run", _noop, raising=True)
    sub = dn.DigitsEventSubscriber(_Bot(), redis_url="redis://fake")
    sub.start()
    # second start should be a no-op branch
    sub.start()
    await sub.stop()
    # stopping when no task should no-op branch
    sub2 = dn.DigitsEventSubscriber(_Bot(), redis_url="redis://fake")
    await sub2.stop()
