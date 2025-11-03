from __future__ import annotations

from types import SimpleNamespace

import pytest
import src.clubbot.cogs.digits as digits_mod
from src.clubbot.cogs.digits import DigitsCog
from src.clubbot.config import Config
from src.clubbot.services.handai.client import HandwritingAPIError


class _FakeInteraction:
    def __init__(self, ack_ok: bool = True) -> None:
        self.response = SimpleNamespace(is_done=lambda: True, defer=lambda **_: None)

        async def _send(*_a: object, **_k: object) -> None:  # followup
            return None

        self.followup = SimpleNamespace(send=_send)
        self._ack_ok = ack_ok


class _FakeService:
    def __init__(self) -> None:
        self.max_image_bytes = 1024 * 1024
        self._err: Exception | None = None
        self._res = SimpleNamespace(
            digit=7,
            confidence=0.9,
            probs=(0.1,) * 10,
            model_id="m",
            uncertain=False,
            latency_ms=10,
        )

    def set_error(self, e: Exception | None) -> None:
        self._err = e

    async def read_image(self, **_kw: object):
        if self._err is not None:
            raise self._err
        return self._res


def _cfg() -> Config:
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
        DIGITS_PUBLIC_RESPONSES=False,
        HANDWRITING_API_URL="https://api",
        HANDWRITING_API_KEY=None,
        HANDWRITING_API_TIMEOUT_SECONDS=1,
        HANDWRITING_API_MAX_RETRIES=0,
        DIGITS_MAX_IMAGE_MB=1,
        TRANSCRIPT_PROVIDER="youtube",
        OPENAI_API_KEY="x",
    )


@pytest.mark.asyncio
async def test_read_early_ack_return(monkeypatch: pytest.MonkeyPatch) -> None:
    # Force ack to return False
    class _Cog(DigitsCog):
        async def _ack_interaction(self, *_: object, **__: object) -> bool:
            return False

    inter = _FakeInteraction()
    cfg = _cfg()
    cog = _Cog(bot=SimpleNamespace(), config=cfg, service=_FakeService())
    await cog.read.callback(cog, inter, SimpleNamespace())  # returns early


@pytest.mark.asyncio
async def test_read_user_id_none_triggers_user_error(monkeypatch: pytest.MonkeyPatch) -> None:
    messages: list[str] = []

    class _Cog(DigitsCog):
        async def handle_user_error(self, interaction, log, message: str) -> None:
            messages.append(message)

    inter = _FakeInteraction()
    inter.user = SimpleNamespace()  # missing id
    cfg = _cfg()
    cog = _Cog(bot=SimpleNamespace(), config=cfg, service=_FakeService())
    await cog.read.callback(cog, inter, SimpleNamespace())
    assert messages


@pytest.mark.asyncio
async def test_read_handles_api_and_generic_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    messages: list[str] = []

    class _Cog(DigitsCog):
        async def handle_user_error(self, interaction, log, message: str) -> None:
            messages.append(message)

        async def handle_exception(self, interaction, log, exc: Exception) -> None:
            messages.append("exc")

    cfg = _cfg()
    svc = _FakeService()
    inter = _FakeInteraction()
    inter.user = SimpleNamespace(id=1)
    # 4xx path -> user error
    cog = _Cog(bot=SimpleNamespace(), config=cfg, service=svc)
    svc.set_error(HandwritingAPIError(400, "bad", code="invalid_image"))

    async def _read() -> bytes:
        return b""

    await cog.read.callback(
        cog,
        inter,
        SimpleNamespace(content_type="image/png", filename="x", read=_read),
    )
    # generic exception path -> handle_exception
    svc.set_error(RuntimeError("boom"))

    async def _read2() -> bytes:
        return b""

    await cog.read.callback(
        cog,
        inter,
        SimpleNamespace(content_type="image/png", filename="x", read=_read2),
    )
    # 5xx path -> handle_exception via HandwritingAPIError
    svc.set_error(HandwritingAPIError(500, "oops"))
    await cog.read.callback(
        cog,
        inter,
        SimpleNamespace(content_type="image/png", filename="x", read=_read2),
    )
    assert messages and any(m for m in messages if m == "exc")


def test_extract_int_attr_and_validate_attachment_size() -> None:
    cfg = _cfg()
    cog = DigitsCog(bot=SimpleNamespace(), config=cfg, service=_FakeService())
    assert cog._extract_int_attr(None, "id") is None

    class _A:
        def __init__(self, size: int) -> None:
            self.content_type = "image/png"
            self.size = size

    att = _A(size=(cfg.DIGITS_MAX_IMAGE_MB * 1024 * 1024) + 1)
    with pytest.raises(digits_mod.UserInputError):
        cog._validate_attachment(att)
