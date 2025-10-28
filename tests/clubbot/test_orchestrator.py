import os
from types import SimpleNamespace
from typing import Any

import pytest
from src.clubbot.config import Config
from src.clubbot.container import ServiceContainer
from src.clubbot.orchestrator import BotOrchestrator
from src.clubbot.services.qr_app import QRService


def make_cfg(guild_ids=None) -> Config:
    return Config(
        DISCORD_TOKEN="test",
        DISCORD_GUILD_ID=None,
        DISCORD_GUILD_IDS=list(guild_ids or []),
        LOG_LEVEL="INFO",
        QRCODE_RATE_LIMIT=1,
        QRCODE_RATE_WINDOW_SECONDS=1,
        QR_DEFAULT_ERROR_CORRECTION="M",
        QR_DEFAULT_BOX_SIZE=10,
        QR_DEFAULT_BORDER=2,
        QR_DEFAULT_FILL_COLOR="#000000",
        QR_DEFAULT_BACK_COLOR="#FFFFFF",
        QR_PUBLIC_RESPONSES=True,
    )


@pytest.mark.asyncio
async def test_on_ready_triggers_sync_commands():
    # Ensure startup sync is enabled for this test environment
    os.environ["COMMANDS_SYNC_ON_START"] = "true"
    cfg = Config(
        DISCORD_TOKEN="test",
        DISCORD_GUILD_ID=None,
        DISCORD_GUILD_IDS=[],
        LOG_LEVEL="INFO",
        QRCODE_RATE_LIMIT=1,
        QRCODE_RATE_WINDOW_SECONDS=1,
        QR_DEFAULT_ERROR_CORRECTION="M",
        QR_DEFAULT_BOX_SIZE=10,
        QR_DEFAULT_BORDER=2,
        QR_DEFAULT_FILL_COLOR="#000000",
        QR_DEFAULT_BACK_COLOR="#FFFFFF",
        QR_PUBLIC_RESPONSES=True,
        COMMANDS_SYNC_GLOBAL=True,
    )
    from src.clubbot.services.metrics import NullMetricsService

    container = ServiceContainer(cfg=cfg, qr_service=QRService(cfg), metrics=NullMetricsService())
    orch = BotOrchestrator(container)
    bot = orch.build_bot()

    calls: list[dict[str, Any]] = []

    async def fake_tree_sync(*, guild: object | None = None) -> list[object]:
        calls.append({"guild": guild})
        return []

    bot.tree.sync = fake_tree_sync
    orch.register_listeners()
    ready = orch._on_ready_listener
    assert ready is not None
    await ready()

    assert len(calls) == 1 and calls[0]["guild"] is None


@pytest.mark.asyncio
async def test_sync_commands_global_only():
    # With global-only design, sync() is called once globally
    os.environ.pop("COMMANDS_SYNC_ON_START", None)
    cfg = Config(
        DISCORD_TOKEN="test",
        DISCORD_GUILD_ID=None,
        DISCORD_GUILD_IDS=[],
        LOG_LEVEL="INFO",
        QRCODE_RATE_LIMIT=1,
        QRCODE_RATE_WINDOW_SECONDS=1,
        QR_DEFAULT_ERROR_CORRECTION="M",
        QR_DEFAULT_BOX_SIZE=10,
        QR_DEFAULT_BORDER=2,
        QR_DEFAULT_FILL_COLOR="#000000",
        QR_DEFAULT_BACK_COLOR="#FFFFFF",
        QR_PUBLIC_RESPONSES=True,
        COMMANDS_SYNC_GLOBAL=True,
    )
    from src.clubbot.services.metrics import NullMetricsService

    container = ServiceContainer(cfg=cfg, qr_service=QRService(cfg), metrics=NullMetricsService())
    orch = BotOrchestrator(container)
    bot = orch.build_bot()

    # Patch tree.sync to observe calls
    calls: list[SimpleNamespace] = []

    async def fake_tree_sync_global(*, guild: object | None = None) -> list[object]:
        calls.append(SimpleNamespace(guild=guild))
        return []

    bot.tree.sync = fake_tree_sync_global

    await orch.sync_commands()

    assert len(calls) == 1 and calls[0].guild is None


@pytest.mark.asyncio
async def test_on_guild_join_no_per_guild_sync():
    # No per-guild sync should occur on join; global-only model
    cfg = make_cfg([555])
    from src.clubbot.services.metrics import NullMetricsService

    container = ServiceContainer(cfg=cfg, qr_service=QRService(cfg), metrics=NullMetricsService())
    orch = BotOrchestrator(container)
    bot = orch.build_bot()
    orch.register_listeners()

    calls: list[SimpleNamespace] = []

    async def fake_tree_sync_join(*, guild: object | None = None) -> list[object]:
        calls.append(SimpleNamespace(guild=guild))
        return []

    bot.tree.sync = fake_tree_sync_join

    # Invoke listener directly
    join_listener = orch._on_guild_join_listener
    assert join_listener is not None
    guild = SimpleNamespace(id=555, name="Target")
    await join_listener(guild)
    assert calls == []


@pytest.mark.asyncio
async def test_global_sync_runs_once_on_boot():
    # Trigger startup sync
    os.environ["COMMANDS_SYNC_ON_START"] = "true"
    # Create a config with global sync enabled and no target guilds
    cfg = Config(
        DISCORD_TOKEN="test",
        DISCORD_GUILD_ID=None,
        DISCORD_GUILD_IDS=[],
        LOG_LEVEL="INFO",
        QRCODE_RATE_LIMIT=1,
        QRCODE_RATE_WINDOW_SECONDS=1,
        QR_DEFAULT_ERROR_CORRECTION="M",
        QR_DEFAULT_BOX_SIZE=10,
        QR_DEFAULT_BORDER=2,
        QR_DEFAULT_FILL_COLOR="#000000",
        QR_DEFAULT_BACK_COLOR="#FFFFFF",
        QR_PUBLIC_RESPONSES=True,
        COMMANDS_SYNC_GLOBAL=True,
    )

    from src.clubbot.services.metrics import NullMetricsService

    container = ServiceContainer(cfg=cfg, qr_service=QRService(cfg), metrics=NullMetricsService())
    orch = BotOrchestrator(container)
    bot = orch.build_bot()

    calls: list[SimpleNamespace] = []

    async def fake_tree_sync_boot(*, guild: object | None = None) -> list[object]:
        calls.append(SimpleNamespace(guild=guild))
        return []

    bot.tree.sync = fake_tree_sync_boot
    orch.register_listeners()

    # First ready should perform a global sync
    ready_listener = orch._on_ready_listener
    assert ready_listener is not None
    await ready_listener()
    assert len(calls) == 1 and calls[0].guild is None

    # Subsequent ready should not sync again
    await ready_listener()
    assert len(calls) == 1
