from __future__ import annotations

import asyncio

import pytest

from clubbot.services.jobs.trainer_notifier import TrainerEventSubscriber


@pytest.mark.asyncio
async def test_trainer_notifier_start_stop(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Bot:
        async def fetch_user(self, user_id: int):  # pragma: no cover - not used
            raise RuntimeError("not needed")

    sub = TrainerEventSubscriber(bot=_Bot(), redis_url="redis://example")

    async def _noop_run(self) -> None:
        await asyncio.sleep(0)

    monkeypatch.setattr(TrainerEventSubscriber, "_run", _noop_run)

    sub.start()
    # idempotent start
    sub.start()
    await sub.stop()


@pytest.mark.asyncio
async def test_trainer_notifier_stop_without_start() -> None:
    class _Bot:
        async def fetch_user(self, user_id: int):  # pragma: no cover - not used
            raise RuntimeError("not needed")

    sub = TrainerEventSubscriber(bot=_Bot(), redis_url="redis://example")
    # Should return early when no task is running
    await sub.stop()
