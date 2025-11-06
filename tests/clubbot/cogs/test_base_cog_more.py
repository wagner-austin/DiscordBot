from __future__ import annotations

import io
from typing import no_type_check

import discord
import pytest
from src.clubbot.cogs.base import BaseCog


class _Resp:
    def __init__(self, done: bool, raise_on_send: bool = False) -> None:
        self._done = done
        self._raise = raise_on_send
        self.sent: list[tuple[str, dict[str, object]]] = []

    def is_done(self) -> bool:
        return self._done

    async def send_message(self, msg: str, **kw: object) -> None:
        if self._raise:
            raise RuntimeError("boom")
        self.sent.append((msg, kw))


class _Follow:
    def __init__(self) -> None:
        self.sent: list[tuple[str, dict[str, object]]] = []

    async def send(self, msg: str, **kw: object) -> None:
        self.sent.append((msg, kw))


class _Interaction:
    def __init__(self, done: bool, raise_on_send: bool = False) -> None:
        self._resp = _Resp(done, raise_on_send=raise_on_send)
        self._follow = _Follow()

    @property
    def response(self) -> _Resp:
        return self._resp

    @property
    def followup(self) -> _Follow:
        return self._follow


@pytest.mark.asyncio
async def test_handle_user_error_sends_on_response_or_followup() -> None:
    cog = BaseCog()
    # response path
    inter = _Interaction(done=False)
    log = cog.request_logger("r1")

    @no_type_check
    async def _call() -> None:
        await cog.handle_user_error(inter, log, "msg")

    await _call()
    assert getattr(inter.response, "sent", []) and not getattr(inter.followup, "sent", [])
    # followup fallback path
    inter2 = _Interaction(done=False, raise_on_send=True)

    @no_type_check
    async def _call2() -> None:
        await cog.handle_user_error(inter2, log, "msg2")

    await _call2()
    assert getattr(inter2.followup, "sent", [])


@pytest.mark.asyncio
async def test_handle_exception_includes_req_and_branches() -> None:
    cog = BaseCog()
    inter = _Interaction(done=True)
    log = cog.request_logger("r99")

    @no_type_check
    async def _call3() -> None:
        await cog.handle_exception(inter, log, RuntimeError("x"))

    await _call3()
    sent_follow = getattr(inter.followup, "sent", [])
    assert sent_follow and "req=r99" in sent_follow[0][0]
    # else branch when not done
    inter2 = _Interaction(done=False)

    @no_type_check
    async def _call4() -> None:
        await cog.handle_exception(inter2, log, RuntimeError("y"))

    await _call4()
    assert getattr(inter2.response, "sent", [])


@pytest.mark.asyncio
async def test_handle_exception_ignores_nondict_extra() -> None:
    # Ensure branch where logger.extra is not a dict is covered
    cog = BaseCog()

    class _Log:
        def __init__(self) -> None:
            self.extra = "nondict"

        def exception(self, *args: object, **kwargs: object) -> None:  # pragma: no cover - trivial
            return None

    class _Resp:
        def is_done(self) -> bool:
            return True

    class _Follow:
        def __init__(self) -> None:
            self.sent: list[tuple[str, dict[str, object]]] = []

        async def send(self, content: str, **kw: object) -> None:
            self.sent.append((content, kw))

    class _Interaction:
        def __init__(self) -> None:
            self.response = _Resp()
            self.followup = _Follow()

    inter = _Interaction()

    async def _call() -> None:
        await cog.handle_exception(inter, _Log(), RuntimeError("x"))

    await _call()
    # Message should not include req= suffix since extra is non-dict
    assert inter.followup.sent and "req=" not in inter.followup.sent[0][0]


@pytest.mark.asyncio
async def test_dm_file_and_notify_user_bot_none_and_failure_paths() -> None:
    cog = BaseCog()
    # bot is None path
    cog.bot = None
    await cog.notify_user(1, "x")
    await cog.dm_file(1, "x", discord.File(fp=io.BytesIO(b"x"), filename="x.txt"))


@pytest.mark.asyncio
async def test_dm_file_success_path() -> None:
    cog = BaseCog()

    class _User:
        def __init__(self) -> None:
            self.sent: list[tuple[str, object]] = []

        async def send(self, content: str, **kw: object) -> None:
            self.sent.append((content, kw.get("file")))

    class _Bot:
        def __init__(self) -> None:
            self._u = _User()

        async def fetch_user(self, _uid: int) -> _User:
            return self._u

    bot = _Bot()
    cog.bot = bot
    dummy_file = discord.File(fp=io.BytesIO(b"x"), filename="x.txt")
    await cog.dm_file(7, "hello", dummy_file)
    assert bot._u.sent and bot._u.sent[-1][0] == "hello" and bot._u.sent[-1][1] is dummy_file

    # failure path: fetch_user raises
    class _FailBot:
        async def fetch_user(self, *_: object, **__: object) -> object:
            raise RuntimeError("nope")

    cog.bot = _FailBot()
    await cog.notify_user(1, "x")
    await cog.dm_file(1, "x", discord.File(fp=io.BytesIO(b"x"), filename="x.txt"))
