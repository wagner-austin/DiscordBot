from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from types import SimpleNamespace

import pytest
from src.clubbot.orchestrator import BotOrchestrator


class _FakeResp:
    def __init__(self, done: bool) -> None:
        self._done = done
        self.sent: list[tuple[str, dict[str, object]]] = []

    def is_done(self) -> bool:
        return self._done

    async def send_message(self, content: str, **kw: object) -> None:
        self.sent.append((content, kw))


class _FakeFollowup:
    def __init__(self) -> None:
        self.sent: list[tuple[str, dict[str, object]]] = []

    async def send(self, content: str, **kw: object) -> None:
        self.sent.append((content, kw))


def _build_orchestrator() -> BotOrchestrator:
    cfg = SimpleNamespace(
        DISCORD_TOKEN="t.t.t",
        LOG_LEVEL="INFO",
        COMMANDS_SYNC_GLOBAL=False,
        DISCORD_GUILD_IDS=[],
    )
    cont = SimpleNamespace(cfg=cfg, wire_bot_async=lambda bot: asyncio.sleep(0))
    orch = BotOrchestrator(cont)
    orch.build_bot()
    return orch


def test_on_app_command_error_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    orch = _build_orchestrator()

    captured: dict[str, Callable[..., Awaitable[None]]] = {}

    def capture_add_listener(func: Callable[..., Awaitable[None]], name: str | None = None) -> None:
        key = name or func.__name__
        captured[key] = func

    monkeypatch.setattr(orch.bot, "add_listener", capture_add_listener, raising=True)
    orch.register_listeners()
    handler = captured["on_application_command_error"]

    class _Interaction:
        def __init__(self, done: bool) -> None:
            self.response = _FakeResp(done)
            self.followup = _FakeFollowup()

    # When response.is_done is True -> followup.send
    inter1 = _Interaction(done=True)
    asyncio.get_event_loop().run_until_complete(handler(inter1, RuntimeError("x")))
    assert inter1.followup.sent and not inter1.response.sent

    # When response.is_done is False -> response.send_message
    inter2 = _Interaction(done=False)
    asyncio.get_event_loop().run_until_complete(handler(inter2, RuntimeError("y")))
    assert inter2.response.sent


@pytest.mark.asyncio
async def test_setup_hook_invokes_wiring_and_register(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = SimpleNamespace(
        DISCORD_TOKEN="t.t.t",
        LOG_LEVEL="INFO",
        COMMANDS_SYNC_GLOBAL=False,
        DISCORD_GUILD_IDS=[],
    )
    calls = {"wired": False, "registered": False}
    cont = SimpleNamespace(
        cfg=cfg,
        wire_bot_async=lambda bot: asyncio.sleep(0) if not calls.update({"wired": True}) else None,
    )
    orch = BotOrchestrator(cont)

    def reg() -> None:
        calls["registered"] = True

    monkeypatch.setattr(orch, "register_listeners", reg, raising=True)
    bot = orch.build_bot()
    await bot.setup_hook()
    assert calls["wired"] and calls["registered"]


def test_sync_commands_exception_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    orch = _build_orchestrator()

    class _ForbiddenError(Exception):
        pass

    class _HTTPError(Exception):
        pass

    import src.clubbot.orchestrator as orch_mod

    monkeypatch.setattr(
        orch_mod,
        "discord",
        SimpleNamespace(Forbidden=_ForbiddenError, HTTPException=_HTTPError),
        raising=True,
    )

    async def raise_forbidden() -> bool:
        raise _ForbiddenError()

    async def raise_http() -> bool:
        raise _HTTPError()

    monkeypatch.setattr(orch, "_sync_global", raise_forbidden, raising=True)
    asyncio.get_event_loop().run_until_complete(orch.sync_commands())
    monkeypatch.setattr(orch, "_sync_global", raise_http, raising=True)
    with pytest.raises(_HTTPError):
        asyncio.get_event_loop().run_until_complete(orch.sync_commands())


def test_on_ready_sync_toggle(monkeypatch: pytest.MonkeyPatch) -> None:
    orch = _build_orchestrator()
    captured: dict[str, Callable[..., Awaitable[None]]] = {}

    def capture(func: Callable[..., Awaitable[None]], name: str | None = None) -> None:
        captured[name or func.__name__] = func

    monkeypatch.setattr(orch.bot, "add_listener", capture, raising=True)
    orch.register_listeners()
    on_ready = captured["on_ready"]

    monkeypatch.setenv("COMMANDS_SYNC_ON_START", "false")
    asyncio.get_event_loop().run_until_complete(on_ready())

    monkeypatch.setenv("COMMANDS_SYNC_ON_START", "true")
    called = {"n": 0}

    async def fake_sync() -> None:
        called["n"] += 1

    monkeypatch.setattr(orch, "sync_commands", fake_sync, raising=True)
    asyncio.get_event_loop().run_until_complete(on_ready())
    assert called["n"] == 1


def test_preflight_app_id_mismatch_debug_no_raise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = SimpleNamespace(DISCORD_TOKEN="MTIz.x.y")
    orch = BotOrchestrator(SimpleNamespace(cfg=cfg))
    monkeypatch.setenv("DISCORD_APPLICATION_ID", "999")
    # Mismatch path is non-fatal; logs debug and returns
    orch._preflight_token_check()


def test_run_calls_build_and_bot_run(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = SimpleNamespace(DISCORD_TOKEN="tkn")
    orch = BotOrchestrator(SimpleNamespace(cfg=cfg))
    called = {"token": None}

    class _FakeBot:
        def run(self, token: str) -> None:
            called["token"] = token

    monkeypatch.setattr(orch, "build_bot", lambda: _FakeBot(), raising=True)
    orch.run()
    assert called["token"] == "tkn"
