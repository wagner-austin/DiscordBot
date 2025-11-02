from __future__ import annotations

from types import SimpleNamespace

import pytest
import src.clubbot.cogs.transcript as transcript_mod
from src.clubbot.cogs.transcript import TranscriptCog
from src.clubbot.config import Config


class _FakeBot:
    async def fetch_user(self, user_id: int):  # pragma: no cover - not used here
        return SimpleNamespace(send=lambda *a, **k: None)


class _FakeService:
    def __init__(self) -> None:
        self.provider = SimpleNamespace()


def _cfg_stt() -> Config:
    return Config(
        DISCORD_TOKEN="test",
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
        TRANSCRIPT_PUBLIC_RESPONSES=False,
        TRANSCRIPT_PROVIDER="stt",
        OPENAI_API_KEY="x",
        REDIS_URL="redis://fake",
    )


def test_transcript_cog_initializes_rq_enqueuer_and_subscriber(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bot = _FakeBot()
    cfg = _cfg_stt()
    service = _FakeService()

    created: dict[str, object] = {}

    class _FakeEnq:
        def __init__(self, *, redis_url: str, **_: object) -> None:
            created["redis_url"] = redis_url

        def enqueue_transcript(self, **kwargs: object) -> str:  # pragma: no cover - not used
            return "job-id"

    class _FakeSub:
        def __init__(self, *_: object, **__: object) -> None:
            created["subscriber"] = True
            self._started = False

        def start(self) -> None:
            self._started = True
            created["started"] = True

    monkeypatch.setattr(transcript_mod, "RQTranscriptEnqueuer", _FakeEnq, raising=True)
    monkeypatch.setattr(transcript_mod, "TranscriptEventSubscriber", _FakeSub, raising=True)

    _ = TranscriptCog(bot=bot, config=cfg, transcript_service=service)
    assert created.get("redis_url") == "redis://fake"
    assert created.get("subscriber") and created.get("started")
