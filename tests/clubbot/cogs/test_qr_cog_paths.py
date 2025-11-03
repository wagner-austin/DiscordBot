from __future__ import annotations

from types import SimpleNamespace
from typing import no_type_check

import pytest
import src.clubbot.cogs.qr as qr_mod
from src.clubbot.cogs.qr import QRCog
from src.clubbot.config import Config


class _FakeInteraction:
    def __init__(self) -> None:
        async def _send(*_a: object, **_k: object) -> None:
            return None

        async def _defer(**_kw: object) -> None:
            return None

        self.response = SimpleNamespace(is_done=lambda: False, defer=_defer)
        self.followup = SimpleNamespace(send=_send)
        self.user = SimpleNamespace(id=0)


class _FakeService:
    def __init__(self) -> None:
        self._res = SimpleNamespace(image_png=b"x", url="https://x")

    def generate_qr_with_options(
        self, *_: object, **__: object
    ) -> object:  # sync, called in thread
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
        TRANSCRIPT_PROVIDER="youtube",
        OPENAI_API_KEY="x",
    )


@pytest.mark.asyncio
@no_type_check
async def test_qr_ack_return_and_user_id_none(monkeypatch: pytest.MonkeyPatch) -> None:
    # Force ack false to hit early return
    class _Cog(QRCog):
        async def _ack_interaction(self, *_: object, **__: object) -> bool:
            return False

    cfg = _cfg()
    cog = _Cog(bot=SimpleNamespace(), config=cfg, qr_service=_FakeService())

    @no_type_check
    async def _call() -> None:
        await cog.qrcode.callback(cog, _FakeInteraction(), "https://x")

    await _call()

    # user id None path
    messages: list[str] = []

    class _Cog2(QRCog):
        async def handle_user_error(self, interaction: object, log: object, message: str) -> None:
            messages.append(message)

    inter = _FakeInteraction()
    inter.user = SimpleNamespace()  # missing id
    cog2 = _Cog2(bot=SimpleNamespace(), config=cfg, qr_service=_FakeService())

    @no_type_check
    async def _call2() -> None:
        await cog2.qrcode.callback(cog2, inter, "https://x")

    await _call2()
    assert messages


@pytest.mark.asyncio
@no_type_check
async def test_qr_ack_exceptions(monkeypatch: pytest.MonkeyPatch) -> None:
    # Patch discord module exceptions in qr module
    class _NotFoundError(Exception):
        pass

    class _HTTPError(Exception):
        def __init__(self, code: int) -> None:
            self.code = code

    monkeypatch.setattr(
        qr_mod,
        "discord",
        SimpleNamespace(NotFound=_NotFoundError, HTTPException=_HTTPError),
    )

    cfg = _cfg()
    cog = QRCog(bot=SimpleNamespace(), config=cfg, qr_service=_FakeService())

    class _Resp:
        def __init__(self, to_raise: Exception | None) -> None:
            self._raise = to_raise

        def is_done(self) -> bool:
            return False

        async def defer(self, **_kw: object) -> None:
            if self._raise:
                raise self._raise

    async def _noop(*_a: object, **_k: object) -> None:
        return None

    inter = _FakeInteraction()
    inter.response = _Resp(_NotFoundError("x"))
    ok = await cog._ack_interaction(inter)
    assert ok is False

    inter2 = _FakeInteraction()
    inter2.response = _Resp(_HTTPError(40060))
    ok2 = await cog._ack_interaction(inter2)
    assert ok2 is True

    inter3 = _FakeInteraction()
    inter3.response = _Resp(_HTTPError(499))
    inter3.followup = SimpleNamespace(send=_noop)
    ok3 = await cog._ack_interaction(inter3)
    assert ok3 is False


def test_qr_extract_attr_and_setup(monkeypatch: pytest.MonkeyPatch) -> None:
    assert QRCog._extract_int_attr(None, "id") is None

    added: dict[str, bool] = {}

    class _FakeBot:
        async def add_cog(self, cog: object) -> None:
            added["ok"] = True

    monkeypatch.setattr(qr_mod, "load_config", lambda: _cfg())
    monkeypatch.setattr(qr_mod, "QRService", lambda cfg: _FakeService())
    import asyncio as _asyncio

    _asyncio.get_event_loop().run_until_complete(qr_mod.setup(_FakeBot()))
    assert added.get("ok") is True
