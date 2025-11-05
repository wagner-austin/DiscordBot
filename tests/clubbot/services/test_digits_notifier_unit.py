from __future__ import annotations

import asyncio
from types import SimpleNamespace

import discord
import pytest
import src.clubbot.services.jobs.digits_notifier as dn


class _User:
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def send(self, message: str) -> object:  # pragma: no cover - trivial
        self.messages.append(message)
        return SimpleNamespace()


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
        }
    )
    assert any("Training started" in m for m in bot.user.messages)

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
    assert any("Training progress" in m for m in bot.user.messages)

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
    assert any("Training completed" in m for m in bot.user.messages)

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
    assert any("Training failed" in m for m in bot.user.messages)

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
    assert any("An error occurred during training" in m for m in bot.user.messages)


@pytest.mark.asyncio
async def test_notify_handles_discord_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    class _BadUser:
        async def send(self, message: str) -> object:  # pragma: no cover - trivial
            _ = message

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
