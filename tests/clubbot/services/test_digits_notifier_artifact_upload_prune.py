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
async def test_handle_artifact_event_noop() -> None:
    """Test that artifact events are handled without crashing (no-op)."""
    bot = _Bot()
    sub = dn.DigitsEventSubscriber(bot, redis_url="redis://fake")

    await sub._handle_event(
        {
            "type": "digits.train.artifact.v1",
            "request_id": "r_art",
            "user_id": 200,
            "model_id": "mnist",
            "run_id": "2025-01-01T12:00:00",
            "ts": "2025-01-01T12:00:00Z",
            "path": "/artifacts/digits/models/mnist_resnet18_v1",
        }
    )
    # Artifact handler is a no-op, should not send messages
    assert len(bot.user.embeds) == 0


@pytest.mark.asyncio
async def test_handle_upload_event_noop() -> None:
    """Test that upload events are handled without crashing (no-op)."""
    bot = _Bot()
    sub = dn.DigitsEventSubscriber(bot, redis_url="redis://fake")

    await sub._handle_event(
        {
            "type": "digits.train.upload.v1",
            "request_id": "r_upload",
            "user_id": 201,
            "model_id": "mnist",
            "run_id": "2025-01-01T12:00:00",
            "ts": "2025-01-01T12:05:00Z",
            "status": 200,
            "model_bytes": 45678901,
            "manifest_bytes": 1234,
        }
    )
    # Upload handler is a no-op, should not send messages
    assert len(bot.user.embeds) == 0


@pytest.mark.asyncio
async def test_handle_upload_event_with_error_status() -> None:
    """Test that upload events with error status are handled (no-op currently)."""
    bot = _Bot()
    sub = dn.DigitsEventSubscriber(bot, redis_url="redis://fake")

    await sub._handle_event(
        {
            "type": "digits.train.upload.v1",
            "request_id": "r_upload_err",
            "user_id": 202,
            "model_id": "mnist",
            "run_id": "2025-01-01T12:00:00",
            "ts": "2025-01-01T12:05:00Z",
            "status": 500,  # Error status
            "model_bytes": 0,
            "manifest_bytes": 0,
        }
    )
    # Upload handler is a no-op even for errors, should not send messages
    assert len(bot.user.embeds) == 0


@pytest.mark.asyncio
async def test_handle_prune_event_noop() -> None:
    """Test that prune events are handled without crashing (no-op)."""
    bot = _Bot()
    sub = dn.DigitsEventSubscriber(bot, redis_url="redis://fake")

    await sub._handle_event(
        {
            "type": "digits.train.prune.v1",
            "request_id": "r_prune",
            "user_id": 203,
            "model_id": "mnist",
            "run_id": "2025-01-01T12:00:00",
            "ts": "2025-01-01T12:10:00Z",
            "deleted_count": 3,
        }
    )
    # Prune handler is a no-op, should not send messages
    assert len(bot.user.embeds) == 0


@pytest.mark.asyncio
async def test_handle_prune_event_zero_deleted() -> None:
    """Test that prune events with zero deletions are handled (no-op)."""
    bot = _Bot()
    sub = dn.DigitsEventSubscriber(bot, redis_url="redis://fake")

    await sub._handle_event(
        {
            "type": "digits.train.prune.v1",
            "request_id": "r_prune_zero",
            "user_id": 204,
            "model_id": "mnist",
            "run_id": "2025-01-01T12:00:00",
            "ts": "2025-01-01T12:10:00Z",
            "deleted_count": 0,
        }
    )
    # Prune handler is a no-op, should not send messages
    assert len(bot.user.embeds) == 0


@pytest.mark.asyncio
async def test_on_artifact_direct_call() -> None:
    """Test direct call to _on_artifact method."""
    bot = _Bot()
    sub = dn.DigitsEventSubscriber(bot, redis_url="redis://fake")

    await sub._on_artifact(user_id=205, request_id="r_art_direct", path="/path/to/artifact")
    # Should not crash and not send messages
    assert len(bot.user.embeds) == 0


@pytest.mark.asyncio
async def test_on_upload_direct_call() -> None:
    """Test direct call to _on_upload method."""
    bot = _Bot()
    sub = dn.DigitsEventSubscriber(bot, redis_url="redis://fake")

    await sub._on_upload(
        user_id=206,
        request_id="r_upload_direct",
        status=200,
        model_bytes=1000,
        manifest_bytes=100,
    )
    # Should not crash and not send messages
    assert len(bot.user.embeds) == 0


@pytest.mark.asyncio
async def test_on_prune_direct_call() -> None:
    """Test direct call to _on_prune method."""
    bot = _Bot()
    sub = dn.DigitsEventSubscriber(bot, redis_url="redis://fake")

    await sub._on_prune(user_id=207, request_id="r_prune_direct", deleted_count=5)
    # Should not crash and not send messages
    assert len(bot.user.embeds) == 0
