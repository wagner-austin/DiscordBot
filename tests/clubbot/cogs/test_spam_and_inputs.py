import asyncio
import time
from types import SimpleNamespace
from typing import Any, Protocol, no_type_check

import discord
import pytest
from discord.ext import commands
from src.clubbot.cogs.qr import QRCog
from src.clubbot.config import Config


class FakeResponse:
    def __init__(self, parent: "FakeInteraction") -> None:
        self._done = False
        self._parent = parent

    def is_done(self) -> bool:
        return self._done

    async def defer(self, *, ephemeral: bool = False) -> None:
        self._done = True

    async def send_message(self, content: str = "", *, ephemeral: bool = False) -> None:
        self._done = True
        self._parent.calls.append({"message": content, "file": None, "ephemeral": ephemeral})


class FakeFollowup:
    def __init__(self, parent: "FakeInteraction") -> None:
        self._parent = parent

    async def send(
        self, content: str = "", *, file: discord.File | None = None, ephemeral: bool = False
    ) -> None:
        self._parent.calls.append({"message": content, "file": file, "ephemeral": ephemeral})


class FakeInteraction:
    def __init__(self, uid: int) -> None:
        self.calls: list[dict[str, Any]] = []
        self.user = SimpleNamespace(id=uid)
        self.response = FakeResponse(self)
        self.followup = FakeFollowup(self)


def make_cfg(per: int = 1000, window: int = 1) -> Config:
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
        QR_PUBLIC_RESPONSES=True,
    )


class _Opts(Protocol):
    url: str


class SlowQRService:
    def __init__(self, delay: float = 0.1) -> None:
        self.delay = delay

    def generate_qr_with_options(self, opts: _Opts) -> object:  # pragma: no cover - simple stub
        # Simulate CPU/PIL work without blocking the event loop
        time.sleep(self.delay)
        return type("QRResult", (), {"image_png": b"\x89PNG\r\n\x1a\n", "url": opts.url})()


@pytest.mark.asyncio
async def test_qrcode_spam_concurrent_calls_complete_without_errors() -> None:
    intents = discord.Intents.default()
    bot = commands.Bot(command_prefix="!", intents=intents)
    cfg = make_cfg(per=1000, window=1)
    svc = SlowQRService(delay=0.05)
    cog = QRCog(bot, cfg, svc)

    # Launch many concurrent calls with unique users to avoid rate limiter
    n = 10
    ctxs = [FakeInteraction(uid=i + 1) for i in range(n)]

    @no_type_check
    async def run_one(c) -> None:
        await cog.qrcode.callback(cog, c, "example.com")

    await asyncio.gather(*(run_one(c) for c in ctxs))

    # Every call should have produced a response with a file
    assert all(c.calls for c in ctxs)
    assert all(c.calls[-1]["file"] is not None for c in ctxs)


@pytest.mark.asyncio
async def test_qrcode_handles_various_invalid_inputs_with_clear_messages() -> None:
    intents = discord.Intents.default()
    bot = commands.Bot(command_prefix="!", intents=intents)
    cfg = make_cfg(per=1000, window=1)
    from src.clubbot.services.qr_app import QRService

    cog = QRCog(bot, cfg, QRService(cfg))

    bad_inputs = [
        "msn",  # missing TLD
        "msn. c om",  # spaces within host
        "msncom",  # not a valid domain
    ]

    for raw in bad_inputs:
        ctx = FakeInteraction(uid=42)

        @no_type_check
        async def _call(ctx_local: FakeInteraction, raw_local: str) -> None:
            await cog.qrcode.callback(cog, ctx_local, raw_local)

        await _call(ctx, raw)
        assert ctx.calls, f"Expected an error response for input: {raw!r}"
        msg = str(ctx.calls[-1]["message"]) or ""
        # Accept our validation message families (friendlier wording allowed)
        assert (
            ("Please provide" in msg)
            or ("Invalid URL" in msg)
            or ("URL host is required" in msg)
            or ("Please check the URL and try again." in msg)
        )
