from __future__ import annotations

from types import SimpleNamespace

import pytest
import src.clubbot.cogs.transcript as t_mod
from src.clubbot.cogs.transcript import TranscriptCog
from src.clubbot.config import Config


def _cfg(provider: str = "youtube", redis_url: str | None = "redis://fake") -> Config:
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
        REDIS_URL=redis_url,
        TRANSCRIPT_MAX_FILE_MB=25,
        TRANSCRIPT_ENABLE_CHUNKING=False,
        TRANSCRIPT_MAX_VIDEO_SECONDS=60,
    )


class _FakeInteraction:
    def __init__(self, done: bool = False) -> None:
        async def _send(*_a: object, **_k: object) -> None:
            return None

        async def _defer(**_kw: object) -> None:
            return None

        self.response = SimpleNamespace(is_done=lambda: done, defer=_defer)
        self.followup = SimpleNamespace(send=_send)
        self.user = SimpleNamespace(id=1)


def test_init_stt_requires_redis() -> None:
    with pytest.raises(RuntimeError):
        TranscriptCog(
            bot=SimpleNamespace(),
            config=_cfg(provider="stt", redis_url=""),
            transcript_service=SimpleNamespace(),
        )


@pytest.mark.asyncio
async def test_transcript_rate_limited(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Cog(TranscriptCog):
        pass

    cfg = _cfg()
    cog = _Cog(bot=SimpleNamespace(), config=cfg, transcript_service=SimpleNamespace())
    # Force rate limiter deny
    cog.rate_limiter = SimpleNamespace(allow=lambda *_: (False, 7))  # type: ignore[assignment]
    inter = _FakeInteraction()
    monkeypatch.setattr(t_mod, "validate_youtube_url", lambda u: u)
    await cog.transcript.callback(cog, inter, "https://example.com/watch?v=1")


@pytest.mark.asyncio
async def test_transcript_stt_delegate(monkeypatch: pytest.MonkeyPatch) -> None:
    hit: dict[str, bool] = {"called": False}

    class _Cog(TranscriptCog):
        async def _handle_stt_request(self, **_: object) -> bool:
            hit["called"] = True
            return True

    cfg = _cfg(provider="stt")
    # Avoid subscriber/runner side-effects
    monkeypatch.setattr(
        t_mod,
        "TranscriptEventSubscriber",
        lambda *a, **k: SimpleNamespace(start=lambda: None, stop=lambda: None),
    )

    # No JobRunner in STT path; only subscriber runs in bot process

    cog = _Cog(bot=SimpleNamespace(), config=cfg, transcript_service=SimpleNamespace())
    inter = _FakeInteraction()
    inter.user = SimpleNamespace(id=2)
    monkeypatch.setattr(t_mod, "validate_youtube_url", lambda u: u)
    await cog.transcript.callback(cog, inter, "https://example.com/watch?v=2")
    assert hit["called"] is True


@pytest.mark.asyncio
async def test_ack_already_done_returns_true() -> None:
    cfg = _cfg()
    cog = TranscriptCog(bot=SimpleNamespace(), config=cfg, transcript_service=SimpleNamespace())
    inter = _FakeInteraction(done=True)
    ok = await cog._ack_interaction(inter)
    assert ok is True


@pytest.mark.asyncio
async def test_transcript_user_id_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    messages: list[str] = []

    class _Cog(TranscriptCog):
        async def handle_user_error(self, interaction, log, message: str) -> None:  # type: ignore[override]
            messages.append(message)

    cfg = _cfg()
    cog = _Cog(bot=SimpleNamespace(), config=cfg, transcript_service=SimpleNamespace())
    inter = _FakeInteraction()
    inter.user = SimpleNamespace()  # missing id
    await cog.transcript.callback(cog, inter, "https://example.com/watch?v=3")
    assert messages


@pytest.mark.asyncio
async def test_transcript_ack_early_return(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Cog(TranscriptCog):
        async def _ack_interaction(self, *_: object, **__: object) -> bool:
            return False

    cfg = _cfg()
    cog = _Cog(bot=SimpleNamespace(), config=cfg, transcript_service=SimpleNamespace())
    await cog.transcript.callback(cog, _FakeInteraction(), "https://example.com/watch?v=4")


@pytest.mark.asyncio
async def test_transcript_user_input_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.clubbot.utils.errors import UserInputError

    messages: list[str] = []

    class _Cog(TranscriptCog):
        async def handle_user_error(self, interaction, log, message: str) -> None:  # type: ignore[override]
            messages.append(message)

    cfg = _cfg()
    cog = _Cog(bot=SimpleNamespace(), config=cfg, transcript_service=SimpleNamespace())
    inter = _FakeInteraction()

    def _raise(_u: str) -> str:
        raise UserInputError("bad")

    monkeypatch.setattr(t_mod, "validate_youtube_url", _raise)
    await cog.transcript.callback(cog, inter, "https://example.com/watch?v=5")
    assert messages


@pytest.mark.asyncio
async def test_transcript_generic_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    hits: list[str] = []

    class _Svc:
        def fetch_cleaned(self, url: str):  # sync, called via to_thread
            raise RuntimeError("boom")

    class _Cog(TranscriptCog):
        async def handle_exception(self, interaction, log, exc: Exception) -> None:  # type: ignore[override]
            hits.append("exc")

    cfg = _cfg()
    cog = _Cog(bot=SimpleNamespace(), config=cfg, transcript_service=_Svc())
    inter = _FakeInteraction()
    inter.user = SimpleNamespace(id=3)
    monkeypatch.setattr(t_mod, "validate_youtube_url", lambda u: u)
    await cog.transcript.callback(cog, inter, "https://example.com/watch?v=6")
    assert hits


@pytest.mark.asyncio
async def test_handle_stt_no_backend_raises() -> None:
    cfg = _cfg()
    svc = SimpleNamespace(provider=SimpleNamespace())
    cog = TranscriptCog(bot=SimpleNamespace(), config=cfg, transcript_service=svc)
    inter = _FakeInteraction()
    import logging as _logging

    log = _logging.LoggerAdapter(_logging.getLogger(__name__), {})
    with pytest.raises(RuntimeError):
        await cog._handle_stt_request(
            interaction=inter, log=log, url="https://x", req_id="r1", user_id=1
        )


@pytest.mark.asyncio
async def test_handle_stt_eta_provider_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    # Build a fake STTTranscriptProvider class and instance with estimate + estimate_eta_minutes
    calls: dict[str, bool] = {"eta": False}

    class _FakeSTT:
        def estimate(self, url: str) -> tuple[int, float]:
            # Keep under default TRANSCRIPT_MAX_VIDEO_SECONDS (60) to avoid early-return
            return 30, 3.0

        def estimate_eta_minutes(self, dur_s: int, approx_mb: float) -> int:
            calls["eta"] = True
            return 7

    import importlib

    mod = importlib.import_module("src.clubbot.services.transcript.stt_provider")
    monkeypatch.setattr(mod, "STTTranscriptProvider", _FakeSTT, raising=False)
    svc = SimpleNamespace(provider=_FakeSTT())

    # Avoid Redis by stubbing subscriber; inject a fake enqueuer
    monkeypatch.setattr(
        t_mod,
        "TranscriptEventSubscriber",
        lambda *a, **k: SimpleNamespace(start=lambda: None, stop=lambda: None),
    )

    class _FakeEnq:
        def __init__(self) -> None:
            self.called = False

        def enqueue_transcript(self, *, request_id: str, url: str, user_id: int) -> str:
            self.called = True
            return "job-eta"

    enq = _FakeEnq()
    cfg = _cfg(provider="stt")
    cog = TranscriptCog(bot=SimpleNamespace(), config=cfg, transcript_service=svc, enqueuer=enq)
    inter = _FakeInteraction()
    import logging as _logging

    log = _logging.LoggerAdapter(_logging.getLogger(__name__), {})
    ok = await cog._handle_stt_request(
        interaction=inter, log=log, url="https://x", req_id="r2", user_id=9
    )
    assert ok is True and calls["eta"] is True
