import asyncio
from types import SimpleNamespace
from typing import Any

import discord
import pytest
from discord.ext import commands
from src.clubbot.cogs.transcript import TranscriptCog
from src.clubbot.config import Config
from src.clubbot.services.jobs.queue import MemoryJobQueue, TranscriptJob
from src.clubbot.services.transcript.types import TranscriptResult


class FakeProvider:
    def estimate(self, url: str) -> tuple[int, float]:  # duration, approx_mb
        return (600, 8.0)


class FakeTranscriptService:
    def __init__(self) -> None:
        self.provider = FakeProvider()

    def fetch_cleaned(self, url: str) -> TranscriptResult:
        return TranscriptResult(url=url, video_id="abc123xyz00", text="hello world")


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


class FakeUser:
    def __init__(self) -> None:
        self.dm: list[dict[str, Any]] = []

    async def send(self, content: str, file: discord.File | None = None) -> None:
        self.dm.append({"message": content, "file": file})


class FakeInteraction:
    def __init__(self, uid: int) -> None:
        self.calls: list[dict[str, Any]] = []
        self.user = SimpleNamespace(id=uid)
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
        TRANSCRIPT_PROVIDER="stt",
        OPENAI_API_KEY="test",
    )


@pytest.mark.asyncio
async def test_transcript_stt_enqueues_and_dms_user(monkeypatch: pytest.MonkeyPatch) -> None:
    intents = discord.Intents.default()
    bot = commands.Bot(command_prefix="!", intents=intents)
    cfg = make_cfg()
    svc = FakeTranscriptService()
    cog = TranscriptCog(bot, cfg, svc, queue=MemoryJobQueue[TranscriptJob]())

    # Patch bot.fetch_user to capture DM
    fake_user = FakeUser()

    async def fake_fetch_user(uid: int) -> FakeUser:  # type: ignore[override]
        return fake_user

    monkeypatch.setattr(bot, "fetch_user", fake_fetch_user)  # type: ignore[arg-type]

    interaction = FakeInteraction(uid=42)
    await cog.transcript.callback(cog, interaction, "https://youtu.be/abc123xyz00")

    # Immediate response should indicate queued job and show estimate
    assert interaction.calls, "Expected a response"
    first = interaction.calls[-1]
    assert "Queued transcription" in (first.get("message") or "")

    # Let background worker process (test queue); wait up to ~2.5s
    for _ in range(50):
        if fake_user.dm:
            break
        await asyncio.sleep(0.05)
    assert fake_user.dm, "Expected a DM with the transcript"
    dm_last = fake_user.dm[-1]
    msg = dm_last["message"]
    assert msg.startswith("Transcript for <") and "abc123xyz00" in msg

    # Cleanup runner to avoid warnings
    if hasattr(cog, "_runner"):
        await cog._runner.stop()  # type: ignore[attr-defined]
