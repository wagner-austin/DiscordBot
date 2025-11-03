from __future__ import annotations

import pytest
from src.clubbot.container import ServiceContainer
from src.clubbot.orchestrator import BotOrchestrator


@pytest.mark.asyncio
async def test_sync_global_respects_disabled_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISCORD_TOKEN", "x")
    monkeypatch.setenv("COMMANDS_SYNC_GLOBAL", "false")
    orchestrator = BotOrchestrator(ServiceContainer.from_env())
    orchestrator.build_bot()
    ok = await orchestrator._sync_global()
    assert ok is False
