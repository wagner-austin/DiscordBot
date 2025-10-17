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


class FakeResponse:
    def __init__(self, parent: "FakeInteraction") -> None:
        self._done = False
        self._parent = parent

    def is_done(self) -> bool:  # type: ignore[override]
        return self._done

    async def defer(self, *, ephemeral: bool = False):  # type: ignore[no-untyped-def]
        self._done = True

    async def send_message(self, content: str = "", *, ephemeral: bool = False):  # type: ignore[no-untyped-def]
        self._done = True
        self._parent.calls.append({"message": content, "file": None, "ephemeral": ephemeral})


class FakeFollowup:
    def __init__(self, parent: "FakeInteraction") -> None:
        self._parent = parent

    async def send(self, content: str = "", *, file=None, ephemeral: bool = False):  # type: ignore[no-untyped-def]
        self._parent.calls.append({"message": content, "file": file, "ephemeral": ephemeral})


class FakeInteraction:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.user = SimpleNamespace(id=123456)
        self.response = FakeResponse(self)
        self.followup = FakeFollowup(self)


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
        QR_PUBLIC_RESPONSES=True,
    )


@pytest.mark.asyncio
async def test_qrcode_accepts_bare_hostname_and_replies_with_file():
    intents = discord.Intents.default()
    bot = commands.Bot(command_prefix="!", intents=intents)
    cfg = make_cfg(per=1_000_000, window=1)
    from src.clubbot.services.qr_app import QRService

    svc = QRService(cfg)
    cog = QRCog(bot, cfg, svc)
    interaction = FakeInteraction()
    await cog.qrcode.callback(cog, interaction, "example.com")

    assert interaction.calls, "Expected a respond call"
    last = interaction.calls[-1]
    assert last["file"] is not None


@pytest.mark.asyncio
async def test_qrcode_invalid_url_returns_user_message():
    intents = discord.Intents.default()
    bot = commands.Bot(command_prefix="!", intents=intents)
    cfg = make_cfg()
    from src.clubbot.services.qr_app import QRService

    svc = QRService(cfg)
    cog = QRCog(bot, cfg, svc)
    interaction = FakeInteraction()
    await cog.qrcode.callback(cog, interaction, "not a url with spaces")

    assert interaction.calls, "Expected a respond call"
    last = interaction.calls[-1]
    msg = str(last["message"]) or ""
    # Accept legacy and friendlier validation messages
    assert (
        ("Invalid URL" in msg)
        or ("Please provide" in msg)
        or ("Please check the URL and try again." in msg)
    )
    assert last["ephemeral"] is True


@pytest.mark.asyncio
async def test_qrcode_rate_limit_message_on_second_call():
    intents = discord.Intents.default()
    bot = commands.Bot(command_prefix="!", intents=intents)
    cfg = make_cfg(per=1, window=1)
    svc = FakeQRService()
    cog = QRCog(bot, cfg, svc)
    interaction = FakeInteraction()
    await cog.qrcode.callback(cog, interaction, "https://example.com")
    await cog.qrcode.callback(cog, interaction, "https://example.com")

    # Second call should be a rate-limit message
    assert len(interaction.calls) >= 2
    last = interaction.calls[-1]
    assert isinstance(last["message"], str) and last["message"].startswith("Please wait ")
    # Ephemeral behavior follows configuration
    assert last["ephemeral"] == (not cfg.QR_PUBLIC_RESPONSES)


@pytest.mark.asyncio
async def test_qrcode_handles_internal_exception_with_generic_message():
    intents = discord.Intents.default()
    bot = commands.Bot(command_prefix="!", intents=intents)
    cfg = make_cfg(per=1_000_000, window=1)
    svc = FakeQRService(fail=True)
    cog = QRCog(bot, cfg, svc)
    interaction = FakeInteraction()
    await cog.qrcode.callback(cog, interaction, "https://example.com")

    assert interaction.calls, "Expected a respond call"
    last = interaction.calls[-1]
    assert last["message"] == "An error occurred. Please try again later."
    assert last["ephemeral"] is True
