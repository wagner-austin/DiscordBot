from __future__ import annotations

from dataclasses import dataclass

import discord
import pytest
from src.clubbot.services.jobs.events import TranscriptCompletedEvent, TranscriptFailedEvent
from src.clubbot.services.jobs.notifier import TranscriptEventSubscriber


class _FakeConn:
    def __init__(self, text: str | None) -> None:
        self._text = text

    async def get(self, name: str) -> str | None:  # pragma: no cover - trivial
        return self._text

    # Provide pubsub API to satisfy notifier protocol (unused by tests)
    class _PS:
        async def subscribe(self, *channels: str) -> None:  # pragma: no cover - stub
            return None

        async def get_message(
            self, ignore_subscribe_messages: bool = True, timeout: float = 1.0
        ) -> dict[str, object] | None:  # pragma: no cover - stub
            return None

        async def close(self) -> None:  # pragma: no cover - stub
            return None

    def pubsub(self) -> _PS:  # pragma: no cover - stub
        return self._PS()


@dataclass
class _Recorder:
    notified: list[tuple[int, str]]
    dm_files: list[tuple[int, str]]


class _TestSubscriber(TranscriptEventSubscriber):
    def __init__(self) -> None:
        class _FakeUser:
            # pragma: no cover - unused
            async def send(self, *args: object, **kwargs: object) -> None:
                return None

        class _FakeBot:
            async def fetch_user(self, user_id: int) -> _FakeUser:  # pragma: no cover - unused
                return _FakeUser()

        super().__init__(bot=_FakeBot(), redis_url="redis://fake")
        self.rec = _Recorder([], [])

    async def _notify(self, user_id: int, message: str) -> None:
        self.rec.notified.append((user_id, message))

    async def _dm_file(self, user_id: int, content: str, file: discord.File) -> None:
        self.rec.dm_files.append((user_id, content))


@pytest.mark.asyncio
async def test_completed_event_dm_file_when_content_present() -> None:
    sub = _TestSubscriber()
    e: TranscriptCompletedEvent = {
        "type": "completed",
        "request_id": "r1",
        "user_id": 7,
        "url": "https://x",
        "video_id": "vid",
        "content_key": "k1",
    }
    conn = _FakeConn("hello")
    await sub._handle_event(conn, e)
    assert sub.rec.dm_files and not sub.rec.notified


@pytest.mark.asyncio
async def test_completed_event_notify_when_missing_content() -> None:
    sub = _TestSubscriber()
    e: TranscriptCompletedEvent = {
        "type": "completed",
        "request_id": "r1",
        "user_id": 7,
        "url": "https://x",
        "video_id": "vid",
        "content_key": "missing",
    }
    conn = _FakeConn(None)
    await sub._handle_event(conn, e)
    assert sub.rec.notified and not sub.rec.dm_files


@pytest.mark.asyncio
async def test_completed_event_too_large_triggers_notify() -> None:
    sub = _TestSubscriber()
    sub.max_attachment_mb = 1
    e: TranscriptCompletedEvent = {
        "type": "completed",
        "request_id": "r1",
        "user_id": 7,
        "url": "https://x",
        "video_id": "vid",
        "content_key": "k1",
    }
    conn = _FakeConn("x" * (2 * 1024 * 1024))
    await sub._handle_event(conn, e)
    assert sub.rec.notified and not sub.rec.dm_files


@pytest.mark.asyncio
async def test_failed_events_notify_user_and_system() -> None:
    sub = _TestSubscriber()
    e_user: TranscriptFailedEvent = {
        "type": "failed",
        "request_id": "r1",
        "user_id": 7,
        "error_kind": "user",
        "message": "m",
    }
    await sub._handle_event(_FakeConn(None), e_user)
    e_system: TranscriptFailedEvent = {
        "type": "failed",
        "request_id": "r1",
        "user_id": 7,
        "error_kind": "system",
        "message": "m",
    }
    await sub._handle_event(_FakeConn(None), e_system)
    assert len(sub.rec.notified) == 2
