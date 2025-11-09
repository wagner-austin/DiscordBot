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
async def test_failed_system_error_memory_pressure_message() -> None:
    """Test that memory pressure errors show specific memory guidance."""
    bot = _Bot()
    sub = dn.DigitsEventSubscriber(bot, redis_url="redis://fake")
    await sub._handle_event(
        {
            "type": "digits.train.failed.v1",
            "request_id": "r_mem_pressure",
            "user_id": 100,
            "model_id": "mnist_mem",
            "run_id": None,
            "ts": "2025-01-01T00:00:00Z",
            "error_kind": "system",
            "message": (
                "Training aborted due to sustained memory pressure (>= 85.0%). "
                "Reduce batch size or DataLoader workers and retry."
            ),
        }
    )
    assert len(bot.user.embeds) == 1
    # Embed should be created with the specific error message


@pytest.mark.asyncio
async def test_failed_system_error_oom_kill_message() -> None:
    """Test that OOM kill errors show specific memory guidance."""
    bot = _Bot()
    sub = dn.DigitsEventSubscriber(bot, redis_url="redis://fake")
    await sub._handle_event(
        {
            "type": "digits.train.failed.v1",
            "request_id": "r_oom",
            "user_id": 101,
            "model_id": "mnist_oom",
            "run_id": None,
            "ts": "2025-01-01T00:00:00Z",
            "error_kind": "system",
            "message": (
                "OOM kill detected (signal 9 / SIGKILL) - "
                "worker terminated by system due to memory exhaustion"
            ),
        }
    )
    assert len(bot.user.embeds) == 1


@pytest.mark.asyncio
async def test_failed_system_error_artifact_upload_message() -> None:
    """Test that artifact upload errors show specific upload guidance."""
    bot = _Bot()
    sub = dn.DigitsEventSubscriber(bot, redis_url="redis://fake")
    await sub._handle_event(
        {
            "type": "digits.train.failed.v1",
            "request_id": "r_upload",
            "user_id": 102,
            "model_id": "mnist_upload",
            "run_id": None,
            "ts": "2025-01-01T00:00:00Z",
            "error_kind": "system",
            "message": "Artifact upload failed: upstream API error. See worker logs for details.",
        }
    )
    assert len(bot.user.embeds) == 1


@pytest.mark.asyncio
async def test_failed_system_error_generic_fallback() -> None:
    """Test that unknown system errors show generic but still helpful guidance."""
    bot = _Bot()
    sub = dn.DigitsEventSubscriber(bot, redis_url="redis://fake")
    await sub._handle_event(
        {
            "type": "digits.train.failed.v1",
            "request_id": "r_generic_sys",
            "user_id": 103,
            "model_id": "mnist_generic",
            "run_id": None,
            "ts": "2025-01-01T00:00:00Z",
            "error_kind": "system",
            "message": "RuntimeError: Something unexpected happened during training",
        }
    )
    assert len(bot.user.embeds) == 1


@pytest.mark.asyncio
async def test_failed_user_error_shows_config_issue() -> None:
    """Test that user errors are labeled as configuration issues."""
    bot = _Bot()
    sub = dn.DigitsEventSubscriber(bot, redis_url="redis://fake")
    await sub._handle_event(
        {
            "type": "digits.train.failed.v1",
            "request_id": "r_user_err",
            "user_id": 104,
            "model_id": "mnist_config",
            "run_id": None,
            "ts": "2025-01-01T00:00:00Z",
            "error_kind": "user",
            "message": "invalid job type",
        }
    )
    assert len(bot.user.embeds) == 1


@pytest.mark.asyncio
async def test_failed_memory_uppercase_detection() -> None:
    """Test that MEMORY in uppercase is also detected."""
    bot = _Bot()
    sub = dn.DigitsEventSubscriber(bot, redis_url="redis://fake")
    await sub._handle_event(
        {
            "type": "digits.train.failed.v1",
            "request_id": "r_mem_upper",
            "user_id": 105,
            "model_id": "m",
            "run_id": None,
            "ts": "t",
            "error_kind": "system",
            "message": "MEMORY allocation failed",
        }
    )
    assert len(bot.user.embeds) == 1


@pytest.mark.asyncio
async def test_failed_upload_case_insensitive_detection() -> None:
    """Test that 'Upload' with capital U is detected."""
    bot = _Bot()
    sub = dn.DigitsEventSubscriber(bot, redis_url="redis://fake")
    await sub._handle_event(
        {
            "type": "digits.train.failed.v1",
            "request_id": "r_upload_cap",
            "user_id": 106,
            "model_id": "m",
            "run_id": None,
            "ts": "t",
            "error_kind": "system",
            "message": "Upload to S3 failed: timeout",
        }
    )
    assert len(bot.user.embeds) == 1


@pytest.mark.asyncio
async def test_failed_message_with_run_id() -> None:
    """Test that failure messages work when run_id is present."""
    bot = _Bot()
    sub = dn.DigitsEventSubscriber(bot, redis_url="redis://fake")
    await sub._handle_event(
        {
            "type": "digits.train.failed.v1",
            "request_id": "r_with_run",
            "user_id": 107,
            "model_id": "mnist_run",
            "run_id": "2025-01-01T12:00:00",
            "ts": "2025-01-01T12:00:00Z",
            "error_kind": "system",
            "message": "Training failed after epoch 5",
        }
    )
    assert len(bot.user.embeds) == 1
