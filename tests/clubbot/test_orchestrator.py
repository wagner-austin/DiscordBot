import os
from types import SimpleNamespace

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
    cfg = make_cfg([])
    from src.clubbot.services.metrics import NullMetricsService

    container = ServiceContainer(cfg=cfg, qr_service=QRService(cfg), metrics=NullMetricsService())
    orch = BotOrchestrator(container)
    orch.build_bot()
    # Cogs not required for this behavior test

    called = False

    async def fake_sync():
        nonlocal called
        called = True

    orch.sync_commands = fake_sync  # type: ignore[assignment]
    orch.register_listeners()
    # Call the on_ready listener directly via orchestrator
    assert hasattr(orch, "_on_ready_listener")
    await orch._on_ready_listener()  # type: ignore[attr-defined]

    assert called is True


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

    async def fake_tree_sync(*, guild=None):  # type: ignore[no-redef]
        calls.append(SimpleNamespace(guild=guild))

    bot.tree.sync = fake_tree_sync  # type: ignore[assignment]

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

    async def fake_tree_sync(*, guild=None):  # type: ignore[no-redef]
        calls.append(SimpleNamespace(guild=guild))

    bot.tree.sync = fake_tree_sync  # type: ignore[assignment]

    # Invoke listener directly
    assert hasattr(orch, "_on_guild_join_listener")
    guild = SimpleNamespace(id=555, name="Target")
    await orch._on_guild_join_listener(guild)  # type: ignore[attr-defined]
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

    async def fake_tree_sync(*, guild=None):  # type: ignore[no-redef]
        calls.append(SimpleNamespace(guild=guild))

    bot.tree.sync = fake_tree_sync  # type: ignore[assignment]
    orch.register_listeners()

    # First ready should perform a global sync
    assert hasattr(orch, "_on_ready_listener")
    await orch._on_ready_listener()  # type: ignore[attr-defined]
    assert len(calls) == 1 and calls[0].guild is None

    # Subsequent ready should not sync again
    await orch._on_ready_listener()  # type: ignore[attr-defined]
    assert len(calls) == 1
