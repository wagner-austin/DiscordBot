import asyncio
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
    cfg = make_cfg([])
    container = ServiceContainer(cfg=cfg, qr_service=QRService(cfg))
    orch = BotOrchestrator(container)
    bot = orch.build_bot()
    container.wire_bot(bot)

    called = False

    async def fake_sync():
        nonlocal called
        called = True

    orch.sync_commands = fake_sync  # type: ignore[assignment]
    orch.register_listeners()

    bot.dispatch("ready")
    await asyncio.sleep(0)

    assert called is True


@pytest.mark.asyncio
async def test_sync_commands_only_targets_present_guilds():
    cfg = make_cfg([101, 202])
    container = ServiceContainer(cfg=cfg, qr_service=QRService(cfg))
    orch = BotOrchestrator(container)
    bot = orch.build_bot()

    # Patch get_guild and sync_commands on the bot
    present = SimpleNamespace(id=101)
    bot.get_guild = lambda gid: present if gid == 101 else None  # type: ignore[method-assign]

    calls = []

    async def fake_sync_commands(*, guild_ids=None):  # type: ignore[no-redef]
        calls.append({"guild_ids": guild_ids})

    bot.sync_commands = fake_sync_commands  # type: ignore[assignment]

    await orch.sync_commands()

    assert calls == [{"guild_ids": [101]}]


@pytest.mark.asyncio
async def test_on_guild_join_syncs_only_for_targeted_guilds():
    cfg = make_cfg([555])
    container = ServiceContainer(cfg=cfg, qr_service=QRService(cfg))
    orch = BotOrchestrator(container)
    bot = orch.build_bot()
    orch.register_listeners()

    calls = []

    async def fake_sync_commands(*, guild_ids=None):  # type: ignore[no-redef]
        calls.append({"guild_ids": guild_ids})

    bot.sync_commands = fake_sync_commands  # type: ignore[assignment]

    # Dispatch targeted guild
    guild = SimpleNamespace(id=555, name="Target")
    bot.dispatch("guild_join", guild)
    await asyncio.sleep(0)
    assert calls == [{"guild_ids": [555]}]

    # Dispatch non-targeted guild (should not sync again)
    bot.dispatch("guild_join", SimpleNamespace(id=777, name="Other"))
    await asyncio.sleep(0)
    assert calls == [{"guild_ids": [555]}]
