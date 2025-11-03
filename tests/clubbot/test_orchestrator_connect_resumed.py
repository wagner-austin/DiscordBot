from __future__ import annotations

import pytest
from src.clubbot.container import ServiceContainer
from src.clubbot.orchestrator import BotOrchestrator


@pytest.mark.asyncio
async def test_on_connect_and_resumed_logs(monkeypatch: pytest.MonkeyPatch, caplog) -> None:
    # Minimal container and bot
    monkeypatch.setenv("DISCORD_TOKEN", "x")
    cont = ServiceContainer.from_env()
    orch = BotOrchestrator(cont)
    bot = orch.build_bot()
    captured: dict[str, list] = {"connect": [], "resumed": []}

    def _add_listener(coro, name=None):
        event = (name or getattr(coro, "__name__", "")).removeprefix("on_")
        captured.setdefault(event, []).append(coro)
        # Call through to real add_listener to keep behavior consistent
        return original_add_listener(coro, name=name)

    original_add_listener = bot.add_listener
    monkeypatch.setattr(bot, "add_listener", _add_listener)

    # Register listeners and call captured connect/resumed handlers
    orch.register_listeners()
    for fn in captured.get("connect", []):
        await fn()
    for fn in captured.get("resumed", []):
        await fn()
