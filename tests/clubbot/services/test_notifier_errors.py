from __future__ import annotations

from types import SimpleNamespace

import pytest
import src.clubbot.services.jobs.notifier as notifier_mod
from src.clubbot.services.jobs.notifier import TranscriptEventSubscriber


class _FakeHTTPError(Exception):
    pass


class _FakeForbiddenError(Exception):
    pass


class _FakeNotFoundError(Exception):
    pass


class _FakeBot:
    def __init__(self, behavior: str) -> None:
        self._behavior = behavior

    async def fetch_user(self, user_id: int):
        if self._behavior == "raise":
            raise _FakeHTTPError("boom")
        # return fake user object that raises on send
        return SimpleNamespace(send=_fake_send_raise)


async def _fake_send_raise(*args, **kwargs):
    raise _FakeForbiddenError("no perms")


@pytest.mark.asyncio
async def test_notify_handles_fetch_user_error(monkeypatch: pytest.MonkeyPatch) -> None:
    # Patch discord exceptions used in notifier to our fake types
    monkeypatch.setattr(
        notifier_mod,
        "discord",
        SimpleNamespace(
            HTTPException=_FakeHTTPError,
            Forbidden=_FakeForbiddenError,
            NotFound=_FakeNotFoundError,
        ),
        raising=True,
    )
    sub = TranscriptEventSubscriber(bot=_FakeBot("raise"), redis_url="redis://fake")
    # Should not raise despite fetch_user error
    await sub._notify(7, "msg")


@pytest.mark.asyncio
async def test_dm_file_handles_send_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        notifier_mod,
        "discord",
        SimpleNamespace(
            HTTPException=_FakeHTTPError,
            Forbidden=_FakeForbiddenError,
            NotFound=_FakeNotFoundError,
            File=object,
        ),
        raising=True,
    )
    sub = TranscriptEventSubscriber(bot=_FakeBot("ok"), redis_url="redis://fake")
    # Should not raise despite user.send error
    await sub._dm_file(7, "content", SimpleNamespace())
