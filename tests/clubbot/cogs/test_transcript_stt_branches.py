from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import discord
import pytest
import src.clubbot.cogs.transcript as t_mod
from discord.ext import commands
from src.clubbot.cogs.transcript import TranscriptCog
from src.clubbot.config import Config
from src.clubbot.services.transcript.types import TranscriptResult


class _FakeInteraction:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

        class _Resp:
            def __init__(self, parent: _FakeInteraction) -> None:
                self._done = False
                self._p = parent

            def is_done(self) -> bool:
                return self._done

            async def defer(self, *, ephemeral: bool = False) -> None:
                self._done = True

            async def send_message(self, content: str = "", *, ephemeral: bool = False) -> None:
                self._done = True
                self._p.calls.append({"message": content, "file": None, "ephemeral": ephemeral})

        class _Follow:
            def __init__(self, parent: _FakeInteraction) -> None:
                self._p = parent

            async def send(
                self,
                content: str = "",
                *,
                file: discord.File | None = None,
                ephemeral: bool = False,
            ) -> None:
                self._p.calls.append({"message": content, "file": file, "ephemeral": ephemeral})

        self.response = _Resp(self)
        self.followup = _Follow(self)
        self.user = SimpleNamespace(id=123)


def _cfg(provider: str = "youtube", redis_url: str | None = None) -> Config:
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
    )


class _Svc:
    def __init__(self, *, text: str) -> None:
        self._res = TranscriptResult(
            url="https://www.youtube.com/watch?v=vid",
            video_id="vid",
            text=text,
        )
        self.provider = SimpleNamespace()  # not SupportsEstimate

    def fetch_cleaned(self, url: str) -> TranscriptResult:
        return self._res


@pytest.mark.asyncio
async def test_stt_false_handled_falls_back_to_captions(monkeypatch: pytest.MonkeyPatch) -> None:
    # Create bot/cog with youtube provider (so constructor avoids RQ side-effects)
    intents = discord.Intents.default()
    bot = commands.Bot(command_prefix="!", intents=intents)

    # Patch event subscriber used in __init__ when provider=stt
    class _FakeSub:
        def __init__(self, *a: object, **k: object) -> None:
            pass

        def start(self) -> None:  # pragma: no cover - trivial
            return None

        async def stop(self) -> None:  # pragma: no cover - trivial
            return None

    monkeypatch.setattr(t_mod, "TranscriptEventSubscriber", _FakeSub, raising=True)

    cfg = _cfg(provider="stt", redis_url="redis://fake")
    svc = _Svc(text="ok")
    fake_enqueuer = SimpleNamespace(enqueue_transcript=lambda **_: None)
    cog = TranscriptCog(bot, cfg, svc, enqueuer=fake_enqueuer)

    # Make _handle_stt_request return False to hit else-branch
    async def _fake_handle(**_: object) -> bool:
        return False

    monkeypatch.setattr(cog, "_handle_stt_request", _fake_handle, raising=True)
    # Bypass YouTube validator in this focused branch test
    monkeypatch.setattr(t_mod, "validate_youtube_url", lambda u: u, raising=True)

    inter = _FakeInteraction()
    await cog.transcript.callback(cog, inter, "https://youtu.be/dQw4w9WgXcQ")
    # Should have sent a file via followup (captions path)
    assert inter.calls and inter.calls[-1]["file"] is not None


@pytest.mark.asyncio
async def test_handle_stt_eta_unknown_path(monkeypatch: pytest.MonkeyPatch) -> None:
    intents = discord.Intents.default()
    bot = commands.Bot(command_prefix="!", intents=intents)
    cfg = _cfg(provider="youtube")
    svc = _Svc(text="ok")
    cog = TranscriptCog(bot, cfg, svc)
    # Provide a fake enqueuer to avoid RuntimeError in _handle_stt_request
    cog._enqueuer = SimpleNamespace(enqueue_transcript=lambda **_: None)

    inter = _FakeInteraction()
    log = cog.request_logger("r1")
    await cog._handle_stt_request(
        interaction=inter,
        log=log,
        url="https://x",
        req_id="req1",
        user_id=1,
    )
    # ETA should be unknown when duration is zero
    assert any("ETA ~?" in c.get("message", "") for c in inter.calls)


def test_check_size_limit_no_ffmpeg_returns_message(monkeypatch: pytest.MonkeyPatch) -> None:
    # Build cog with any config; we will override needed config attributes
    intents = discord.Intents.default()
    bot = commands.Bot(command_prefix="!", intents=intents)
    cfg = _cfg(provider="youtube")
    svc = _Svc(text="x")
    cog = TranscriptCog(bot, cfg, svc)
    # Override config fields accessed by _check_size_limit
    cog.config = SimpleNamespace(TRANSCRIPT_MAX_FILE_MB=1, TRANSCRIPT_ENABLE_CHUNKING=True)
    import shutil as _shutil

    monkeypatch.setattr(_shutil, "which", lambda name: None, raising=True)
    msg = cog._check_size_limit(approx_mb=10.0)
    assert isinstance(msg, str) and "exceeds" in msg


def test_check_size_limit_with_chunking_available(monkeypatch: pytest.MonkeyPatch) -> None:
    intents = discord.Intents.default()
    bot = commands.Bot(command_prefix="!", intents=intents)
    cfg = _cfg(provider="youtube")
    svc = _Svc(text="x")
    cog = TranscriptCog(bot, cfg, svc)
    # Overwrite only fields read by helper
    cog.config = SimpleNamespace(TRANSCRIPT_MAX_FILE_MB=1, TRANSCRIPT_ENABLE_CHUNKING=True)
    import shutil as _shutil

    def _which(name: str) -> str:
        return "ok"  # simulate ffmpeg/ffprobe present

    monkeypatch.setattr(_shutil, "which", _which, raising=True)
    msg = cog._check_size_limit(approx_mb=10.0)
    assert msg is None
