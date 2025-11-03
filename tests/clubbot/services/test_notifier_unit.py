from __future__ import annotations

import asyncio

import pytest
from src.clubbot.services.jobs.notifier import TranscriptEventSubscriber


class _User:
    def __init__(self) -> None:
        self.messages: list[tuple[str, dict]] = []

    async def send(self, content: str, **kwargs: object) -> None:
        self.messages.append((content, kwargs))


class _Bot:
    def __init__(self) -> None:
        self.user = _User()

    async def fetch_user(self, user_id: int) -> _User:
        return self.user


@pytest.mark.asyncio
async def test_notifier_start_idempotent_and_stop_cancels(monkeypatch: pytest.MonkeyPatch) -> None:
    # Patch _run to avoid touching Redis
    async def _noop_run(self: TranscriptEventSubscriber) -> None:  # pragma: no cover - trivial stub
        await asyncio.sleep(10)

    monkeypatch.setattr(TranscriptEventSubscriber, "_run", _noop_run, raising=False)

    sub = TranscriptEventSubscriber(bot=_Bot(), redis_url="redis://localhost:6379/0")
    sub.start()
    # Second start is idempotent: early return
    sub.start()
    # Stop cancels and awaits the task
    await sub.stop()


@pytest.mark.asyncio
async def test_notifier_notify_success_path() -> None:
    bot = _Bot()
    sub = TranscriptEventSubscriber(bot=bot, redis_url="redis://localhost:6379/0")
    await sub._notify(123, "hello")
    assert bot.user.messages and bot.user.messages[-1][0] == "hello"


@pytest.mark.asyncio
async def test_notifier_stop_is_noop_when_not_started() -> None:
    sub = TranscriptEventSubscriber(bot=_Bot(), redis_url="redis://localhost:6379/0")
    await sub.stop()  # should not raise


@pytest.mark.asyncio
async def test_handle_event_dispatches_completed_and_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sub = TranscriptEventSubscriber(bot=_Bot(), redis_url="redis://localhost:6379/0")
    flags = {"completed": False, "failed": False}

    async def _done_completed(conn, e):
        flags["completed"] = True

    async def _done_failed(e):
        flags["failed"] = True

    monkeypatch.setattr(sub, "_on_completed", _done_completed)
    monkeypatch.setattr(sub, "_on_failed", _done_failed)
    # Completed path
    await sub._handle_event(
        object(),
        {
            "type": "completed",
            "user_id": 1,
            "request_id": "r",
            "content_key": "k",
            "url": "u",
            "video_id": "v",
        },
    )
    # Failed path
    await sub._handle_event(
        object(),
        {
            "type": "failed",
            "user_id": 1,
            "request_id": "r",
            "error_kind": "system",
            "message": "m",
        },
    )
    assert flags["completed"] is True and flags["failed"] is True


class _ConnMissing:
    async def get(self, name: str) -> str | None:
        return None


class _ConnWithText:
    def __init__(self, text: str) -> None:
        self._text = text

    async def get(self, name: str) -> str | None:
        return self._text


@pytest.mark.asyncio
async def test_on_completed_key_missing_notifies(monkeypatch: pytest.MonkeyPatch) -> None:
    bot = _Bot()
    sub = TranscriptEventSubscriber(bot=bot, redis_url="redis://localhost:6379/0")
    captured: list[str] = []

    async def _notify(uid: int, msg: str) -> None:
        captured.append(msg)

    monkeypatch.setattr(sub, "_notify", _notify)
    e = {
        "type": "completed",
        "user_id": 1,
        "request_id": "r1",
        "content_key": "k",
        "url": "u",
        "video_id": "v",
    }
    await sub._on_completed(_ConnMissing(), e)
    assert any("transcript is ready" in s.lower() for s in captured)


@pytest.mark.asyncio
async def test_on_completed_too_large_triggers_notify(monkeypatch: pytest.MonkeyPatch) -> None:
    sub = TranscriptEventSubscriber(bot=_Bot(), redis_url="redis://localhost:6379/0")
    sub.max_attachment_mb = 1
    text = "x" * (2 * 1024 * 1024)  # 2MB
    captured: list[str] = []

    async def _notify(uid: int, msg: str) -> None:
        captured.append(msg)

    monkeypatch.setattr(sub, "_notify", _notify)
    e = {
        "type": "completed",
        "user_id": 1,
        "request_id": "r2",
        "content_key": "k",
        "url": "u",
        "video_id": "v",
    }
    await sub._on_completed(_ConnWithText(text), e)
    assert any("too large" in s.lower() for s in captured)


@pytest.mark.asyncio
async def test_on_completed_small_sends_file(monkeypatch: pytest.MonkeyPatch) -> None:
    sub = TranscriptEventSubscriber(bot=_Bot(), redis_url="redis://localhost:6379/0")
    data = "hello world"
    sent: dict[str, object] = {}

    async def _dm_file(uid: int, content: str, file) -> None:
        sent["uid"] = uid
        sent["content"] = content
        sent["file"] = file

    monkeypatch.setattr(sub, "_dm_file", _dm_file)
    e = {
        "type": "completed",
        "user_id": 9,
        "request_id": "r3",
        "content_key": "k",
        "url": "https://x",
        "video_id": "vid",
    }
    await sub._on_completed(_ConnWithText(data), e)
    assert sent.get("uid") == 9 and isinstance(sent.get("file"), object)


@pytest.mark.asyncio
async def test_on_failed_user_and_system_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    sub = TranscriptEventSubscriber(bot=_Bot(), redis_url="redis://localhost:6379/0")
    msgs: list[str] = []

    async def _notify(uid: int, msg: str) -> None:
        msgs.append(msg)

    monkeypatch.setattr(sub, "_notify", _notify)
    await sub._on_failed(
        {
            "type": "failed",
            "user_id": 1,
            "request_id": "r4",
            "error_kind": "user",
            "message": "bad",
        }
    )
    await sub._on_failed(
        {
            "type": "failed",
            "user_id": 1,
            "request_id": "r5",
            "error_kind": "system",
            "message": "oops",
        }
    )
    assert any("failed" in s.lower() for s in msgs) and any(
        "error occurred" in s.lower() for s in msgs
    )
