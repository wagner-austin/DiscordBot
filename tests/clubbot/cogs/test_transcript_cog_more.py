from __future__ import annotations

from types import SimpleNamespace

import pytest
import src.clubbot.cogs.transcript as t_mod
from src.clubbot.cogs.transcript import TranscriptCog
from src.clubbot.config import Config


class _FakeInteraction:
    def __init__(self) -> None:
        async def _send(*_a: object, **_k: object) -> None:
            return None

        async def _defer(**_kw: object) -> None:
            return None

        self.response = SimpleNamespace(is_done=lambda: False, defer=_defer)
        self.followup = SimpleNamespace(send=_send)


class _Res:
    def __init__(self, url: str, vid: str, text: str) -> None:
        self.url = url
        self.video_id = vid
        self.text = text


class _Svc:
    def __init__(self, text: str) -> None:
        self._res = _Res("https://v", "vid1", text)
        self.provider = SimpleNamespace()

    def fetch_cleaned(self, url: str) -> _Res:
        return self._res


def _cfg(provider: str = "youtube", attach_mb: int | None = None) -> Config:
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
        TRANSCRIPT_PROVIDER=provider,
        OPENAI_API_KEY="x",
        REDIS_URL="redis://fake",
        TRANSCRIPT_MAX_FILE_MB=1,
        TRANSCRIPT_ENABLE_CHUNKING=False,
        TRANSCRIPT_MAX_VIDEO_SECONDS=60,
        TRANSCRIPT_MAX_ATTACHMENT_MB=(attach_mb if attach_mb is not None else 25),
    )


def test_extract_and_limits() -> None:
    cfg = _cfg()
    svc = _Svc("hello")
    cog = TranscriptCog(bot=SimpleNamespace(), config=cfg, transcript_service=svc)
    assert cog._extract_int_attr(None, "id") is None
    # duration over limit
    msg = cog._check_duration_limit(120)
    assert isinstance(msg, str) and "Maximum allowed" in msg
    # size limit message when chunking disabled
    msg2 = cog._check_size_limit(10.0)
    assert isinstance(msg2, str) and "exceeds" in msg2


@pytest.mark.asyncio
async def test_captions_path_attachment_too_large(monkeypatch: pytest.MonkeyPatch) -> None:
    # Large text to exceed 1 MB
    text = "x" * (2 * 1024 * 1024)
    cfg = _cfg(provider="youtube", attach_mb=1)
    svc = _Svc(text)
    messages: list[str] = []

    class _Cog(TranscriptCog):
        async def handle_user_error(self, interaction, log, message: str) -> None:
            messages.append(message)

    bot = SimpleNamespace()
    # Skip JobRunner by not injecting queue (provider=youtube)
    cog = _Cog(bot=bot, config=cfg, transcript_service=svc)
    inter = _FakeInteraction()
    inter.user = SimpleNamespace(id=1)
    # Bypass URL validator to hit attachment-size branch
    monkeypatch.setattr(t_mod, "validate_youtube_url", lambda u: u)
    await cog.transcript.callback(cog, inter, "https://example.com/watch?v=1")
    assert messages and "too large" in messages[-1]


@pytest.mark.asyncio
async def test_ack_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    class _NotFoundError(Exception):
        pass

    class _HTTPError(Exception):
        def __init__(self, code: int) -> None:
            self.code = code

    monkeypatch.setattr(
        t_mod,
        "discord",
        SimpleNamespace(NotFound=_NotFoundError, HTTPException=_HTTPError),
    )

    cfg = _cfg()
    cog = TranscriptCog(bot=SimpleNamespace(), config=cfg, transcript_service=_Svc("x"))

    class _Resp:
        def __init__(self, err: Exception | None) -> None:
            self._err = err

        def is_done(self) -> bool:
            return False

        async def defer(self, **_kw: object) -> None:
            if self._err:
                raise self._err

    inter = _FakeInteraction()
    inter.response = _Resp(_NotFoundError("gone"))
    ok = await cog._ack_interaction(inter)
    assert ok is False

    inter2 = _FakeInteraction()
    inter2.response = _Resp(_HTTPError(40060))
    ok2 = await cog._ack_interaction(inter2)
    assert ok2 is True

    inter3 = _FakeInteraction()
    inter3.response = _Resp(_HTTPError(499))
    ok3 = await cog._ack_interaction(inter3)
    assert ok3 is False


def test_setup_function(monkeypatch: pytest.MonkeyPatch) -> None:
    added: dict[str, bool] = {}

    class _FakeBot:
        async def add_cog(self, cog: object) -> None:
            added["ok"] = True

    monkeypatch.setattr(t_mod, "load_config", lambda: _cfg())
    monkeypatch.setattr(t_mod, "TranscriptService", lambda cfg: _Svc("x"))
    import asyncio as _asyncio

    _asyncio.get_event_loop().run_until_complete(t_mod.setup(_FakeBot()))
    assert added.get("ok") is True
