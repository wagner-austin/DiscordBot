from __future__ import annotations

from types import SimpleNamespace

import pytest
import src.clubbot.cogs.digits as digits_mod
from src.clubbot.cogs.digits import DigitsCog
from src.clubbot.config import Config


class _FakeBot:
    async def fetch_user(self, user_id: int):  # pragma: no cover - not used here
        return SimpleNamespace(send=lambda *a, **k: None)


class _FakeService:
    def __init__(self) -> None:
        self.max_image_bytes = 2 * 1024 * 1024


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
        QR_DEFAULT_BORDER=2,
        QR_DEFAULT_FILL_COLOR="#000000",
        QR_DEFAULT_BACK_COLOR="#FFFFFF",
        QR_PUBLIC_RESPONSES=True,
        REDIS_URL="redis://fake",
        DIGITS_PUBLIC_RESPONSES=False,
        DIGITS_RATE_LIMIT=2,
        DIGITS_RATE_WINDOW_SECONDS=60,
        DIGITS_MAX_IMAGE_MB=2,
    )


@pytest.mark.asyncio
async def test_digits_cog_initializes_event_subscriber(monkeypatch: pytest.MonkeyPatch) -> None:
    created: dict[str, object] = {}

    class _FakeSub:
        def __init__(self, bot: object, *, redis_url: str, events_channel: str) -> None:
            _ = bot
            created["redis_url"] = redis_url
            created["events_channel"] = events_channel
            self._started = False

        def start(self) -> None:
            self._started = True
            created["started"] = True

        async def stop(self) -> None:  # pragma: no cover - lifecycle
            created["stopped"] = True

    monkeypatch.setattr(
        __import__("src.clubbot.services.jobs.digits_notifier", fromlist=["DigitsEventSubscriber"]),
        "DigitsEventSubscriber",
        _FakeSub,
        raising=True,
    )

    bot = _FakeBot()
    cfg = _cfg()
    svc = _FakeService()
    _ = DigitsCog(bot, cfg, svc)
    assert created.get("redis_url") == "redis://fake"
    assert created.get("events_channel") == digits_mod.DEFAULT_DIGITS_EVENTS_CHANNEL
    assert created.get("started") is True
