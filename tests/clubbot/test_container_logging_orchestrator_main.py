from __future__ import annotations

import asyncio
import logging
import os
from types import SimpleNamespace

import pytest
import src.clubbot.logging as log_mod
from src.clubbot.main import main as app_main
from src.clubbot.orchestrator import BotOrchestrator


def test_setup_logging_without_rich(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    # Ensure importing rich fails to go through stdlib path
    monkeypatch.setitem(__import__("sys").modules, "rich", None)
    monkeypatch.delenv("BOT_INSTANCE_ID", raising=False)
    caplog.set_level("INFO")
    log_mod.setup_logging("INFO")
    assert log_mod.get_instance_id() != "-"
    # Request-id filter can be applied
    f = log_mod.RequestIdFilter()
    rec = logging.LogRecord("x", logging.INFO, __file__, 1, "m", (), None)
    assert f.filter(rec) is True and hasattr(rec, "request_id")


def test_orchestrator_build_and_listeners(monkeypatch: pytest.MonkeyPatch) -> None:
    # Minimal container with valid token and disabled features
    cfg = SimpleNamespace(
        DISCORD_TOKEN="t.t.t",
        LOG_LEVEL="INFO",
        HANDWRITING_API_URL=None,
        METRICS_ENABLED=False,
        COMMANDS_SYNC_GLOBAL=False,
        DISCORD_GUILD_IDS=[],
    )
    cont = SimpleNamespace(
        cfg=cfg,
        wire_bot_async=lambda bot: asyncio.sleep(0),
    )
    orch = BotOrchestrator(cont)
    bot = orch.build_bot()
    assert bot is orch.bot
    # Register and exercise listeners
    orch.register_listeners()
    assert orch._on_ready_listener is not None


def test_sync_global_and_preflight(monkeypatch: pytest.MonkeyPatch) -> None:
    # Create orchestrator with a bot
    cfg = SimpleNamespace(
        DISCORD_TOKEN="token",
        LOG_LEVEL="INFO",
        COMMANDS_SYNC_GLOBAL=True,
        DISCORD_GUILD_IDS=[],
    )
    cont = SimpleNamespace(cfg=cfg, wire_bot_async=lambda bot: asyncio.sleep(0))
    orch = BotOrchestrator(cont)
    bot = orch.build_bot()

    async def _sync() -> None:
        return None

    monkeypatch.setattr(bot.tree, "sync", _sync, raising=True)

    asyncio.get_event_loop().run_until_complete(orch.sync_commands())
    # Second call to _sync_global returns False due to has_synced flag
    done = asyncio.get_event_loop().run_until_complete(orch._sync_global())
    assert done is False

    # Preflight check with invalid prefixed token raises
    cfg2 = SimpleNamespace(DISCORD_TOKEN="Bot abc", LOG_LEVEL="INFO")
    orch2 = BotOrchestrator(SimpleNamespace(cfg=cfg2))
    with pytest.raises(RuntimeError):
        orch2._preflight_token_check()

    # Application id mismatch path triggers debug (non-fatal)
    cfg3 = SimpleNamespace(DISCORD_TOKEN="abc.def.ghi", LOG_LEVEL="INFO")
    os.environ["DISCORD_APPLICATION_ID"] = "999"
    orch3 = BotOrchestrator(SimpleNamespace(cfg=cfg3))
    orch3.build_bot()
    orch3._preflight_token_check()  # should not raise


def test_main_invokes_orchestrator(monkeypatch: pytest.MonkeyPatch) -> None:
    ran = {"ok": False}

    class _Cont(SimpleNamespace):
        @classmethod
        def from_env(cls):
            return SimpleNamespace(cfg=SimpleNamespace(LOG_LEVEL="INFO", DISCORD_TOKEN="x"))

    class _Orch(SimpleNamespace):
        def __init__(self, container):
            pass

        def run(self) -> None:
            ran["ok"] = True

    monkeypatch.setattr("src.clubbot.main.ServiceContainer", _Cont)
    monkeypatch.setattr("src.clubbot.main.BotOrchestrator", _Orch)
    monkeypatch.setattr("src.clubbot.main.setup_logging", lambda level: None)
    app_main()
    assert ran["ok"] is True
