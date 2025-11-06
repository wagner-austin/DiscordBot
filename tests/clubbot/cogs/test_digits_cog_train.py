from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import discord
import pytest
from discord.ext import commands
from src.clubbot.cogs.digits import DigitsCog
from src.clubbot.config import Config


class FakeService:
    # Minimal service to satisfy constructor; train path does not use it
    def __init__(self) -> None:
        self.max_image_bytes = 2 * 1024 * 1024


class FakeResponse:
    def __init__(self, parent: FakeInteraction) -> None:
        self._done = False
        self._parent = parent

    def is_done(self) -> bool:
        return self._done

    async def defer(self, *, ephemeral: bool = False) -> None:
        self._done = True

    # pragma: no cover - not used in train tests
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
        embed: object | None = None,
        ephemeral: bool = False,
    ) -> None:
        self._parent.calls.append(
            {"message": content, "file": file, "embed": embed, "ephemeral": ephemeral}
        )


class FakeInteraction:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.user = SimpleNamespace(id=321)
        self.response = FakeResponse(self)
        self.followup = FakeFollowup(self)


def make_cfg(public: bool = False) -> Config:
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
        DIGITS_RATE_LIMIT=2,
        DIGITS_RATE_WINDOW_SECONDS=60,
        DIGITS_MAX_IMAGE_MB=2,
    )


class FakeEnqueuer:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def enqueue_train(
        self,
        *,
        request_id: str,
        user_id: int,
        model_id: str,
        epochs: int,
        batch_size: int,
        lr: float,
        seed: int,
        augment: bool,
        notes: str | None = None,
    ) -> str:
        self.calls.append(
            {
                "request_id": request_id,
                "user_id": user_id,
                "model_id": model_id,
                "epochs": epochs,
                "batch_size": batch_size,
                "lr": lr,
                "seed": seed,
                "augment": augment,
                "notes": notes,
            }
        )
        return "job-xyz"


@pytest.mark.asyncio
async def test_train_without_enqueuer_replies_not_configured() -> None:
    intents = discord.Intents.default()
    bot = commands.Bot(command_prefix="!", intents=intents)
    service = FakeService()
    cfg = make_cfg(public=False)
    cog = DigitsCog(bot, cfg, service, enqueuer=None)
    inter = FakeInteraction()
    await cog.train.callback(cog, inter)
    msg = str(inter.calls[-1]["message"]) if inter.calls else ""
    assert "Training is not configured" in msg


@pytest.mark.asyncio
async def test_train_enqueues_and_acknowledges() -> None:
    intents = discord.Intents.default()
    bot = commands.Bot(command_prefix="!", intents=intents)
    service = FakeService()
    cfg = make_cfg(public=False)
    enq = FakeEnqueuer()
    cog = DigitsCog(bot, cfg, service, enqueuer=enq)
    inter = FakeInteraction()
    await cog.train.callback(cog, inter)
    # Verify enqueued with expected defaults and got a confirmation message
    assert enq.calls and isinstance(enq.calls[-1], dict)
    last = inter.calls[-1]
    # Expect an embed-based confirmation with ephemeral delivery
    assert last.get("embed") is not None and last["ephemeral"] is True


@pytest.mark.asyncio
async def test_train_early_ack_return_path() -> None:
    intents = discord.Intents.default()
    bot = commands.Bot(command_prefix="!", intents=intents)
    service = FakeService()
    cfg = make_cfg(public=False)

    class _Cog(DigitsCog):
        async def _ack_interaction(self, interaction: discord.Interaction) -> bool:
            _ = interaction
            return False

    cog = _Cog(bot, cfg, service, enqueuer=None)
    inter = FakeInteraction()
    await cog.train.callback(cog, inter)
    # No messages should be sent when ack fails
    assert inter.calls == []


@pytest.mark.asyncio
async def test_train_user_id_none_triggers_user_error() -> None:
    intents = discord.Intents.default()
    bot = commands.Bot(command_prefix="!", intents=intents)
    service = FakeService()
    cfg = make_cfg(public=False)
    enq = FakeEnqueuer()
    cog = DigitsCog(bot, cfg, service, enqueuer=enq)
    inter = FakeInteraction()
    inter.user = None  # simulate missing id
    await cog.train.callback(cog, inter)
    msg = str(inter.calls[-1]["message"]) if inter.calls else ""
    assert "Could not determine your user id" in msg


@pytest.mark.asyncio
async def test_train_handles_enqueue_exception() -> None:
    intents = discord.Intents.default()
    bot = commands.Bot(command_prefix="!", intents=intents)
    service = FakeService()
    cfg = make_cfg(public=False)

    class _BadEnq(FakeEnqueuer):
        def enqueue_train(
            self,
            *,
            request_id: str,
            user_id: int,
            model_id: str,
            epochs: int,
            batch_size: int,
            lr: float,
            seed: int,
            augment: bool,
            notes: str | None = None,
        ) -> str:
            raise RuntimeError("boom")

    cog = DigitsCog(bot, cfg, service, enqueuer=_BadEnq())
    inter = FakeInteraction()
    await cog.train.callback(cog, inter)
    # Should have sent an error message
    assert inter.calls and "An error occurred" in str(inter.calls[-1]["message"])
