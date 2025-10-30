from types import SimpleNamespace
from typing import Any

import discord
import pytest
from discord.ext import commands
from src.clubbot.cogs.transcript import TranscriptCog
from src.clubbot.config import Config
from src.clubbot.services.jobs.queue import MemoryJobQueue, TranscriptJob
from src.clubbot.services.transcript.types import TranscriptResult


class FakeTranscriptService:
    def __init__(self, text: str = "hello world", vid: str = "dQw4w9WgXcQ") -> None:
        self.text = text
        self.vid = vid

    def fetch_cleaned(self, url: str) -> TranscriptResult:
        return TranscriptResult(
            url="https://www.youtube.com/watch?v=" + self.vid,
            video_id=self.vid,
            text=self.text,
        )


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
        self.calls: list[dict[str, Any]] = []
        self.user = SimpleNamespace(id=123456)
        self.response = FakeResponse(self)
        self.followup = FakeFollowup(self)


def make_cfg() -> Config:
    return Config(
        DISCORD_TOKEN="test",
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
        QR_PUBLIC_RESPONSES=True,
        TRANSCRIPT_PUBLIC_RESPONSES=True,
    )


@pytest.mark.asyncio
async def test_transcript_command_always_responds_with_file():
    intents = discord.Intents.default()
    bot = commands.Bot(command_prefix="!", intents=intents)
    cfg = make_cfg()
    svc = FakeTranscriptService(text="short text")
    cog = TranscriptCog(bot, cfg, svc, queue=MemoryJobQueue[TranscriptJob]())
    interaction = FakeInteraction()
    await cog.transcript.callback(cog, interaction, "https://youtu.be/dQw4w9WgXcQ")

    assert interaction.calls, "Expected a response"
    last = interaction.calls[-1]
    assert last["file"] is not None, "Transcript should always be sent as a file"
