from types import SimpleNamespace

import discord
import pytest
from discord.ext import commands
from src.clubbot.cogs.qr import QRCog
from src.clubbot.config import Config


class FakeQRService:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    def generate_qr(self, url: str):  # pragma: no cover - trivial
        if self.fail:
            raise RuntimeError("boom")
        # Minimal PNG header to avoid pillow dependency here
        return type("QRResult", (), {"image_png": b"\x89PNG\r\n\x1a\n", "url": url})()


class FakeCtx:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.user = SimpleNamespace(id=123456)

    async def respond(self, message=None, file=None, ephemeral=None, **kwargs):  # type: ignore[no-untyped-def]
        # Support both 'message' and 'content' kw for convenience
        content = kwargs.get("content", message)
        self.calls.append({"message": content, "file": file, "ephemeral": ephemeral})


def make_cfg(per: int = 5, window: int = 60) -> Config:
    return Config(
        DISCORD_TOKEN="test",
        DISCORD_GUILD_ID=None,
        DISCORD_GUILD_IDS=[],
        LOG_LEVEL="INFO",
        QRCODE_RATE_LIMIT=per,
        QRCODE_RATE_WINDOW_SECONDS=window,
        QR_DEFAULT_ERROR_CORRECTION="M",
        QR_DEFAULT_BOX_SIZE=10,
        QR_DEFAULT_BORDER=2,
        QR_DEFAULT_FILL_COLOR="#000000",
        QR_DEFAULT_BACK_COLOR="#FFFFFF",
    )


@pytest.mark.asyncio
async def test_qrcode_accepts_bare_hostname_and_replies_with_file():
    intents = discord.Intents.default()
    bot = commands.Bot(intents=intents)
    cfg = make_cfg(per=1_000_000, window=1)
    from src.clubbot.services.qr_app import QRService

    svc = QRService(cfg)
    cog = QRCog(bot, cfg, svc)
    ctx = FakeCtx()

    await cog.qrcode.callback(cog, ctx, "example.com")

    assert ctx.calls, "Expected a respond call"
    last = ctx.calls[-1]
    assert last["file"] is not None and last["ephemeral"] is True


@pytest.mark.asyncio
async def test_qrcode_invalid_url_returns_user_message():
    intents = discord.Intents.default()
    bot = commands.Bot(intents=intents)
    cfg = make_cfg()
    from src.clubbot.services.qr_app import QRService

    svc = QRService(cfg)
    cog = QRCog(bot, cfg, svc)
    ctx = FakeCtx()

    await cog.qrcode.callback(cog, ctx, "not a url with spaces")

    assert ctx.calls, "Expected a respond call"
    last = ctx.calls[-1]
    assert "Invalid URL" in (last["message"] or "") or "Please provide" in (last["message"] or "")
    assert last["ephemeral"] is True


@pytest.mark.asyncio
async def test_qrcode_rate_limit_message_on_second_call():
    intents = discord.Intents.default()
    bot = commands.Bot(intents=intents)
    cfg = make_cfg(per=1, window=1)
    svc = FakeQRService()
    cog = QRCog(bot, cfg, svc)
    ctx = FakeCtx()

    await cog.qrcode.callback(cog, ctx, "https://example.com")
    await cog.qrcode.callback(cog, ctx, "https://example.com")

    # Second call should be a rate-limit message
    assert len(ctx.calls) >= 2
    last = ctx.calls[-1]
    assert isinstance(last["message"], str) and last["message"].startswith("Please wait ")
    assert last["ephemeral"] is True


@pytest.mark.asyncio
async def test_qrcode_handles_internal_exception_with_generic_message():
    intents = discord.Intents.default()
    bot = commands.Bot(intents=intents)
    cfg = make_cfg(per=1_000_000, window=1)
    svc = FakeQRService(fail=True)
    cog = QRCog(bot, cfg, svc)
    ctx = FakeCtx()

    await cog.qrcode.callback(cog, ctx, "https://example.com")

    assert ctx.calls, "Expected a respond call"
    last = ctx.calls[-1]
    assert last["message"] == "An error occurred. Please try again later."
    assert last["ephemeral"] is True
