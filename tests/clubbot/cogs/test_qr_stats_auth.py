import discord
import pytest
from discord.ext import commands
from src.clubbot.cogs.qr_stats import QRStatsCog
from src.clubbot.config import Config


class FakeRole:
    def __init__(self, name: str) -> None:
        self.name = name


class FakeMember:
    def __init__(self, roles: list[FakeRole]) -> None:
        self.roles = roles


class FakeGuild:
    def __init__(self, gid: int) -> None:
        self.id = gid


class FakeCtx:
    def __init__(self, *, user_id: int, guild: FakeGuild | None, member: FakeMember | None) -> None:
        # The slash handler uses both user and author depending on context
        self.user = type("User", (), {"id": user_id})()
        self.author = member
        self.guild = guild
        self.calls: list[dict] = []

    async def respond(self, message=None, embed=None, view=None, ephemeral=None):  # type: ignore[no-untyped-def]
        self.calls.append(
            {
                "message": message,
                "embed": embed,
                "view": view,
                "ephemeral": bool(ephemeral),
            }
        )


class FakeMetrics:
    def summarize_totals(self, window_seconds):  # type: ignore[no-untyped-def]
        return {
            "total_attempts": 5,
            "total_success": 2,
            "unique_users": 1,
            "unique_guilds": 1,
            "unique_links": 1,
        }

    def outcome_breakdown(self, window_seconds):  # type: ignore[no-untyped-def]
        return {"success": 2, "validation_fail": 1, "rate_limited": 1, "internal_error": 1}

    def top_links(self, limit: int, window_seconds):  # type: ignore[no-untyped-def]
        return [{"url": "https://example.com", "count": 2}]


def make_cfg(admin_ids: list[int]) -> Config:
    return Config(
        DISCORD_TOKEN="test",
        DISCORD_GUILD_ID=None,
        DISCORD_GUILD_IDS=[],
        LOG_LEVEL="DEBUG",
        QRCODE_RATE_LIMIT=1,
        QRCODE_RATE_WINDOW_SECONDS=1,
        QR_DEFAULT_ERROR_CORRECTION="M",
        QR_DEFAULT_BOX_SIZE=10,
        QR_DEFAULT_BORDER=2,
        QR_DEFAULT_FILL_COLOR="#000000",
        QR_DEFAULT_BACK_COLOR="#FFFFFF",
        QR_PUBLIC_RESPONSES=True,
        METRICS_ENABLED=True,
        METRICS_SQLITE_PATH="data/metrics.sqlite",
        METRICS_REDACT_QUERY=True,
        QR_STATS_OFFICER_ROLE="officers",
        QR_STATS_DEFAULT_WINDOW="7d",
        QR_STATS_ADMIN_USER_IDS=admin_ids,
        COMMANDS_SYNC_GLOBAL=False,
    )


@pytest.mark.asyncio
async def test_qrstats_dm_admin_allowed():
    intents = discord.Intents.default()
    bot = commands.Bot(intents=intents)
    cfg = make_cfg([999])
    cog = QRStatsCog(bot, cfg, FakeMetrics())
    ctx = FakeCtx(user_id=999, guild=None, member=None)

    await cog.qrstats.callback(cog, ctx)

    assert ctx.calls, "Expected respond to be called"
    last = ctx.calls[-1]
    assert last["embed"].title == "QR Stats"
    assert last["ephemeral"] is True


@pytest.mark.asyncio
async def test_qrstats_dm_non_admin_denied():
    intents = discord.Intents.default()
    bot = commands.Bot(intents=intents)
    cfg = make_cfg([999])
    cog = QRStatsCog(bot, cfg, FakeMetrics())
    ctx = FakeCtx(user_id=123, guild=None, member=None)

    await cog.qrstats.callback(cog, ctx)

    assert ctx.calls, "Expected respond to be called"
    last = ctx.calls[-1]
    assert isinstance(last["message"], str) and "Only Officers" in last["message"]
    assert last["ephemeral"] is True


@pytest.mark.asyncio
async def test_qrstats_guild_admin_allowed():
    intents = discord.Intents.default()
    bot = commands.Bot(intents=intents)
    cfg = make_cfg([555])
    cog = QRStatsCog(bot, cfg, FakeMetrics())
    member = FakeMember([FakeRole("member")])
    ctx = FakeCtx(user_id=555, guild=FakeGuild(42), member=member)

    await cog.qrstats.callback(cog, ctx)

    assert ctx.calls and ctx.calls[-1]["embed"].title == "QR Stats"


@pytest.mark.asyncio
async def test_qrstats_guild_non_officer_denied():
    intents = discord.Intents.default()
    bot = commands.Bot(intents=intents)
    cfg = make_cfg([])
    cog = QRStatsCog(bot, cfg, FakeMetrics())
    member = FakeMember([FakeRole("member")])
    ctx = FakeCtx(user_id=777, guild=FakeGuild(42), member=member)

    await cog.qrstats.callback(cog, ctx)

    assert ctx.calls and "Only Officers" in str(ctx.calls[-1]["message"])
