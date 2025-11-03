from __future__ import annotations

import types

import pytest
from src.clubbot.cogs.base import BaseCog


class _Resp:
    def __init__(self, done: bool) -> None:
        self._done = done
        self.sent: list[tuple[str, dict[str, object]]] = []

    def is_done(self) -> bool:
        return self._done

    async def send_message(self, msg: str, **kw: object) -> None:
        self.sent.append((msg, kw))


class _Follow:
    def __init__(self) -> None:
        self.sent: list[tuple[str, dict[str, object]]] = []

    async def send(self, msg: str, **kw: object) -> None:
        self.sent.append((msg, kw))


class _Interaction:
    def __init__(self, done: bool, raise_on_send: bool = False) -> None:
        self.response = _Resp(done)
        self.followup = _Follow()
        if raise_on_send:

            async def _bad_send_message(msg: str, **kw: object) -> None:
                raise RuntimeError("boom")

            self.response.send_message = _bad_send_message  # type: ignore[assignment]


@pytest.mark.asyncio
async def test_handle_user_error_sends_on_response_or_followup() -> None:
    cog = BaseCog()
    # response path
    inter = _Interaction(done=False)
    log = cog.request_logger("r1")
    await cog.handle_user_error(inter, log, "msg")
    assert inter.response.sent and not inter.followup.sent
    # followup fallback path
    inter2 = _Interaction(done=False, raise_on_send=True)
    await cog.handle_user_error(inter2, log, "msg2")
    assert inter2.followup.sent


@pytest.mark.asyncio
async def test_handle_exception_includes_req_and_branches() -> None:
    cog = BaseCog()
    inter = _Interaction(done=True)
    log = cog.request_logger("r99")
    await cog.handle_exception(inter, log, RuntimeError("x"))
    assert inter.followup.sent and "req=r99" in inter.followup.sent[0][0]
    # else branch when not done
    inter2 = _Interaction(done=False)
    await cog.handle_exception(inter2, log, RuntimeError("y"))
    assert inter2.response.sent


@pytest.mark.asyncio
async def test_dm_file_and_notify_user_bot_none_and_failure_paths() -> None:
    cog = BaseCog()
    # bot is None path
    cog.bot = None  # type: ignore[assignment]
    await cog.notify_user(1, "x")
    await cog.dm_file(1, "x", types.SimpleNamespace())

    # failure path: fetch_user raises
    class _FailBot:
        async def fetch_user(self, *_: object, **__: object):
            raise RuntimeError("nope")

    cog.bot = _FailBot()  # type: ignore[assignment]
    await cog.notify_user(1, "x")
    await cog.dm_file(1, "x", types.SimpleNamespace())
