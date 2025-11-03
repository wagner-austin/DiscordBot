from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import discord
import pytest
from discord.ext import commands
from src.clubbot.cogs.digits import DigitsCog
from src.clubbot.config import Config
from src.clubbot.services.handai.client import PredictResult


class FakeService:
    def __init__(
        self,
        result: PredictResult | None = None,
        raise_exc: Exception | None = None,
    ) -> None:
        self._result = result
        self._raise = raise_exc
        self.max_image_bytes = 2 * 1024 * 1024

    async def read_image(
        self, *, data: bytes, filename: str, content_type: str, request_id: str
    ) -> PredictResult:
        if self._raise is not None:
            raise self._raise
        assert data and filename and content_type and request_id
        return self._result or PredictResult(
            digit=3,
            confidence=0.9,
            probs=tuple(0.9 if i == 3 else 0.01 for i in range(10)),
            model_id="m",
            uncertain=False,
            latency_ms=5,
        )


class FakeResponse:
    def __init__(self, parent: FakeInteraction) -> None:
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
    def __init__(self, parent: FakeInteraction) -> None:
        self._parent = parent

    async def send(
        self,
        content: str = "",
        *,
        file: discord.File | None = None,
        ephemeral: bool = False,
    ) -> None:
        self._parent.calls.append({"message": content, "file": file, "ephemeral": ephemeral})


class FakeInteraction:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.user = SimpleNamespace(id=123)
        self.response = FakeResponse(self)
        self.followup = FakeFollowup(self)


def make_cfg(public: bool = True, limit: int = 5, window: int = 60) -> Config:
    return Config(
        DISCORD_TOKEN="t",
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
        DIGITS_PUBLIC_RESPONSES=public,
        DIGITS_RATE_LIMIT=limit,
        DIGITS_RATE_WINDOW_SECONDS=window,
        DIGITS_MAX_IMAGE_MB=2,
    )


class FakeAttachment(SimpleNamespace):
    async def read(self) -> bytes:  # type: ignore[override]
        return b"image-bytes"


@pytest.mark.asyncio
async def test_read_happy_path_formats_reply() -> None:
    intents = discord.Intents.default()
    bot = commands.Bot(command_prefix="!", intents=intents)
    service = FakeService()
    cfg = make_cfg(public=True)
    cog = DigitsCog(bot, cfg, service)  # type: ignore[arg-type]
    inter = FakeInteraction()
    att = FakeAttachment(filename="d.png", content_type="image/png", size=10)
    await cog.read.callback(cog, inter, att)
    assert inter.calls and "Digit:" in str(inter.calls[-1]["message"])


@pytest.mark.asyncio
async def test_read_rejects_unsupported_type() -> None:
    intents = discord.Intents.default()
    bot = commands.Bot(command_prefix="!", intents=intents)
    service = FakeService()
    cfg = make_cfg()
    cog = DigitsCog(bot, cfg, service)  # type: ignore[arg-type]
    inter = FakeInteraction()
    att = FakeAttachment(filename="x.txt", content_type="text/plain", size=10)
    await cog.read.callback(cog, inter, att)
    last = inter.calls[-1]
    assert "Unsupported file type" in str(last["message"]) and last["ephemeral"] is True


@pytest.mark.asyncio
async def test_read_rate_limit_message_on_second_call() -> None:
    intents = discord.Intents.default()
    bot = commands.Bot(command_prefix="!", intents=intents)
    service = FakeService()
    cfg = make_cfg(limit=1, window=1)
    cog = DigitsCog(bot, cfg, service)  # type: ignore[arg-type]
    inter = FakeInteraction()
    att = FakeAttachment(filename="a.png", content_type="image/png", size=10)
    await cog.read.callback(cog, inter, att)
    await cog.read.callback(cog, inter, att)
    msg = str(inter.calls[-1]["message"])
    assert msg.startswith("Please wait")
