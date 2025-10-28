from dataclasses import replace
from types import SimpleNamespace
from typing import TypedDict

import discord
import pytest
from discord.ext import commands
from src.clubbot.cogs.transcript import TranscriptCog
from src.clubbot.config import Config
from src.clubbot.services.transcript.types import SupportsEstimate


class FakeEstimateProvider:
    def __init__(self, dur_s: int, size_mb: float) -> None:
        self._dur = dur_s
        self._mb = size_mb

    # Must match SupportsEstimate runtime-checkable Protocol
    def estimate(self, url: str) -> tuple[int, float]:
        return self._dur, self._mb


class FakeTranscriptService:
    def __init__(self, provider: SupportsEstimate) -> None:
        self.provider = provider


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
        self,
        content: str = "",
        *,
        file: discord.File | None = None,
        ephemeral: bool = False,
    ) -> None:
        self._parent.calls.append({"message": content, "file": file, "ephemeral": ephemeral})


class FakeInteraction:
    def __init__(self) -> None:
        class CallRec(TypedDict):
            message: str
            file: discord.File | None
            ephemeral: bool

        self.calls: list[CallRec] = []
        self.user = SimpleNamespace(id=42)
        self.response = FakeResponse(self)
        self.followup = FakeFollowup(self)


def make_cfg() -> Config:
    return Config(
        DISCORD_TOKEN="x",
        DISCORD_GUILD_ID=None,
        DISCORD_GUILD_IDS=[],
        LOG_LEVEL="INFO",
        QRCODE_RATE_LIMIT=5,
        QRCODE_RATE_WINDOW_SECONDS=60,
        QR_DEFAULT_ERROR_CORRECTION="M",
        QR_DEFAULT_BOX_SIZE=10,
        QR_DEFAULT_BORDER=2,
        QR_DEFAULT_FILL_COLOR="#000000",
        QR_DEFAULT_BACK_COLOR="#FFFFFF",
        QR_PUBLIC_RESPONSES=False,
        # Transcript-related
        TRANSCRIPT_PUBLIC_RESPONSES=True,
    )


@pytest.mark.asyncio
async def test_stt_preflight_blocks_too_long() -> None:
    intents = discord.Intents.default()
    bot = commands.Bot(command_prefix="!", intents=intents)
    cfg = make_cfg()
    # Configure STT with short max duration to trigger block
    cfg = replace(
        cfg,
        TRANSCRIPT_PROVIDER="stt",
        TRANSCRIPT_MAX_VIDEO_SECONDS=300,
        TRANSCRIPT_MAX_FILE_MB=100,
    )
    svc = FakeTranscriptService(provider=FakeEstimateProvider(dur_s=3600, size_mb=10.0))
    cog = TranscriptCog(bot, cfg, svc)  # starts runner but we won't enqueue
    interaction = FakeInteraction()

    try:
        await cog.transcript.callback(cog, interaction, "https://youtu.be/dQw4w9WgXcQ")
    finally:
        await cog._runner.stop()

    assert interaction.calls, "Expected an error message"
    last = interaction.calls[-1]
    assert isinstance(last.get("message"), str)
    assert "too long" in last["message"].lower()
    assert last["ephemeral"] is True


@pytest.mark.asyncio
async def test_stt_preflight_blocks_too_large() -> None:
    intents = discord.Intents.default()
    bot = commands.Bot(command_prefix="!", intents=intents)
    cfg = make_cfg()
    cfg = replace(
        cfg,
        TRANSCRIPT_PROVIDER="stt",
        TRANSCRIPT_MAX_VIDEO_SECONDS=5400,
        TRANSCRIPT_MAX_FILE_MB=25,
    )
    # Duration okay, size too large (estimated)
    svc = FakeTranscriptService(provider=FakeEstimateProvider(dur_s=120, size_mb=48.0))
    cog = TranscriptCog(bot, cfg, svc)
    interaction = FakeInteraction()

    try:
        await cog.transcript.callback(cog, interaction, "https://youtu.be/dQw4w9WgXcQ")
    finally:
        await cog._runner.stop()

    # Should block on estimated size exceeding Whisper API limit
    assert interaction.calls, "Expected an error message"
    last = interaction.calls[-1]
    assert isinstance(last.get("message"), str)
    msg = last["message"].lower()
    assert "whisper api" in msg or "audio file" in msg
    assert "48 mb" in msg or "25 mb" in msg
    # Error messages are ephemeral
    assert last["ephemeral"] is True
