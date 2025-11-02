from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest
import src.clubbot.cogs.transcript as transcript_mod
from src.clubbot.cogs.transcript import TranscriptCog
from src.clubbot.config import Config


class _FakeNotFoundError(Exception):
    pass


class _FakeInteraction:
    def __init__(self) -> None:
        self.response = SimpleNamespace(is_done=lambda: False, defer=self._defer)
        self.followup = SimpleNamespace(send=lambda *a, **k: None)

    async def _defer(self, *, ephemeral: bool = False) -> None:
        raise _FakeNotFoundError("gone")


class _FakeService:
    def __init__(self) -> None:
        self.provider = SimpleNamespace()


def _cfg_base() -> Config:
    return Config(
        DISCORD_TOKEN="t",
        DISCORD_GUILD_ID=None,
        DISCORD_GUILD_IDS=[],
        LOG_LEVEL="INFO",
        QRCODE_RATE_LIMIT=1,
        QRCODE_RATE_WINDOW_SECONDS=1,
        QR_DEFAULT_ERROR_CORRECTION="M",
        QR_DEFAULT_BOX_SIZE=10,
        QR_DEFAULT_BORDER=1,
        QR_DEFAULT_FILL_COLOR="#000000",
        QR_DEFAULT_BACK_COLOR="#FFFFFF",
        QR_PUBLIC_RESPONSES=False,
        TRANSCRIPT_PUBLIC_RESPONSES=False,
        TRANSCRIPT_PROVIDER="stt",
        OPENAI_API_KEY="x",
        REDIS_URL="redis://fake",
        TRANSCRIPT_MAX_FILE_MB=1,
        TRANSCRIPT_ENABLE_CHUNKING=False,
    )


@pytest.mark.asyncio
async def test_ack_interaction_handles_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    # Patch discord.NotFound used by TranscriptCog._ack_interaction
    monkeypatch.setattr(
        transcript_mod,
        "discord",
        SimpleNamespace(NotFound=_FakeNotFoundError),
        raising=True,
    )
    bot = SimpleNamespace()
    cfg = _cfg_base()
    service = _FakeService()

    # Use injected queue to avoid RQ setup
    cog = TranscriptCog(bot, cfg, service, queue=SimpleNamespace())
    inter = _FakeInteraction()
    ok = await cog._ack_interaction(inter)
    assert ok is False


@pytest.mark.asyncio
async def test_handle_stt_request_size_limit_user_error(monkeypatch: pytest.MonkeyPatch) -> None:
    # Set up provider that estimates too-large audio
    class _Prov:
        def estimate(self, url: str):
            return 600, 100.0  # duration seconds, approx_mb

    service = SimpleNamespace(provider=_Prov())

    # Subclass cog to capture handle_user_error
    messages: list[str] = []

    class _Cog(TranscriptCog):
        async def handle_user_error(self, interaction, log, message: str) -> None:
            messages.append(message)

    cfg = _cfg_base()
    bot = SimpleNamespace()
    cog = _Cog(bot, cfg, service, queue=SimpleNamespace())
    inter = SimpleNamespace()
    log = logging.LoggerAdapter(logging.getLogger(__name__), {})
    handled = await cog._handle_stt_request(
        interaction=inter, log=log, url="https://x", req_id="r1", user_id=7
    )
    assert handled is True and messages, "Expected size-limit user error to be reported"
