from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest
import src.clubbot.cogs.digits as digits_mod
from src.clubbot.cogs.digits import DigitsCog, _format_result, _top_k_indices
from src.clubbot.config import Config
from src.clubbot.services.handai.client import HandwritingAPIError, PredictResult


class _FakeHTTPError(Exception):
    def __init__(self, code: int) -> None:
        super().__init__(f"http {code}")
        self.code = code


class _Inter:
    def __init__(self, exc: Exception | None = None) -> None:
        async def _defer(*, ephemeral: bool = False) -> None:
            if exc is not None:
                raise exc
            return

        self.response = SimpleNamespace(is_done=lambda: False, defer=_defer)
        self.followup = SimpleNamespace(send=lambda *a, **k: None)


def _cfg(public: bool = False) -> Config:
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
        QR_PUBLIC_RESPONSES=True,
        DIGITS_PUBLIC_RESPONSES=public,
        DIGITS_RATE_LIMIT=2,
        DIGITS_RATE_WINDOW_SECONDS=60,
        DIGITS_MAX_IMAGE_MB=1,
    )


class _Svc:
    max_image_bytes = 1 * 1024  # 1KB

    async def read_image(self, **_: object) -> PredictResult:  # pragma: no cover - not used here
        return PredictResult(0, 0.0, (), "m", False, 0)


@pytest.mark.asyncio
async def test_ack_interaction_handles_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    class _NotFoundError(Exception):
        pass

    # Patch discord module in digits cog
    monkeypatch.setattr(
        digits_mod, "discord", SimpleNamespace(NotFound=_NotFoundError), raising=True
    )
    bot = SimpleNamespace()
    cfg = _cfg()
    svc = _Svc()
    cog = DigitsCog(bot, cfg, svc)
    inter = _Inter(exc=_NotFoundError())
    ok = await cog._ack_interaction(inter)
    assert ok is False


@pytest.mark.asyncio
async def test_ack_interaction_http_exception_already_ack(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        digits_mod,
        "discord",
        SimpleNamespace(HTTPException=_FakeHTTPError, NotFound=type("NF", (Exception,), {})),
        raising=True,
    )
    bot = SimpleNamespace()
    cfg = _cfg()
    svc = _Svc()
    cog = DigitsCog(bot, cfg, svc)
    inter = _Inter(exc=_FakeHTTPError(40060))
    ok = await cog._ack_interaction(inter)
    assert ok is True


@pytest.mark.asyncio
async def test_ack_interaction_http_exception_other(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        digits_mod,
        "discord",
        SimpleNamespace(HTTPException=_FakeHTTPError, NotFound=type("NF", (Exception,), {})),
        raising=True,
    )
    bot = SimpleNamespace()
    cfg = _cfg()
    svc = _Svc()
    cog = DigitsCog(bot, cfg, svc)
    inter = _Inter(exc=_FakeHTTPError(1))
    ok = await cog._ack_interaction(inter)
    assert ok is False


@pytest.mark.asyncio
async def test_user_error_mappings_and_size_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    # Subclass cog to capture user messages
    messages: list[str] = []

    class _Cog(DigitsCog):
        async def handle_user_error(self, interaction, log, message: str) -> None:
            messages.append(message)

        async def handle_exception(self, interaction, log, exc: Exception) -> None:
            messages.append("EXC")

    bot = SimpleNamespace()
    cfg = _cfg()
    svc = _Svc()
    cog = _Cog(bot, cfg, svc)

    # Too large preflight
    att = SimpleNamespace(filename="a.png", content_type="image/png", size=10)
    inter = SimpleNamespace()
    log = logging.LoggerAdapter(logging.getLogger(__name__), {})
    from src.clubbot.utils.errors import UserInputError

    try:
        cog._validate_attachment(att)
    except UserInputError as e:
        await cog.handle_user_error(inter, log, str(e))

    # API error mapping examples
    from src.clubbot.cogs.digits import _user_message_from_api_error

    msgs = [
        _user_message_from_api_error(HandwritingAPIError(401, "", code="unauthorized")),
        _user_message_from_api_error(HandwritingAPIError(413, "", code="too_large")),
        _user_message_from_api_error(HandwritingAPIError(415, "", code="unsupported_media_type")),
        _user_message_from_api_error(HandwritingAPIError(400, "", code="invalid_image")),
        _user_message_from_api_error(HandwritingAPIError(504, "", code="timeout")),
        _user_message_from_api_error(HandwritingAPIError(500, "", code=None)),
    ]
    assert any("authorized" in msgs[0].lower() for _ in [0])
    assert any("large" in msgs[1].lower() for _ in [0])
    assert any("unsupported" in msgs[2].lower() for _ in [0])
    assert any("process" in msgs[3].lower() for _ in [0])
    assert any("timed out" in msgs[4].lower() for _ in [0])
    # New behavior: surface API code/message (no generic fallback)
    assert any("internal_error" in msgs[5].lower() or "http" in msgs[5].lower() for _ in [0])


def test_format_helpers() -> None:
    res = PredictResult(
        digit=2,
        confidence=0.6,
        probs=(0.1, 0.2, 0.6, 0.05, 0.05, 0.0, 0.0, 0.0, 0.0, 0.0),
        model_id="m",
        uncertain=True,
        latency_ms=1,
    )
    s = _format_result(res)
    assert "Digit: 2" in s and "Low confidence" in s
    assert _top_k_indices(res.probs, 3) == [2, 1, 0]
