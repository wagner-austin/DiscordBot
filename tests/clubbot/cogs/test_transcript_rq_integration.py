from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest
import src.clubbot.cogs.transcript as transcript_mod
from src.clubbot.cogs.transcript import TranscriptCog
from src.clubbot.config import Config


class _FakeInteraction:
    def __init__(self) -> None:
        async def _send(*_a: object, **_k: object) -> None:
            return None

        self.followup = SimpleNamespace(send=_send)


class _FakeService:
    class _Prov:
        def estimate(self, url: str) -> tuple[int, float]:
            return 60, 1.0  # 1 minute, ~1 MB

    def __init__(self) -> None:
        self.provider = self._Prov()


def _cfg_stt() -> Config:
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
        TRANSCRIPT_MAX_FILE_MB=25,
        TRANSCRIPT_ENABLE_CHUNKING=False,
    )


class _FakeJob:
    def __init__(self, job_id: str) -> None:
        self._id = job_id

    def get_id(self) -> str:
        return self._id


class _FakeQueue:
    def __init__(self, name: str, connection: object) -> None:
        self.name = name
        self.connection = connection
        self.last_args: tuple[object, ...] | None = None
        self.last_kwargs: dict[str, object] | None = None

    def enqueue(self, f: str, payload: dict[str, object], **kwargs: object) -> _FakeJob:
        self.last_args = (f, payload)
        self.last_kwargs = dict(kwargs)
        return _FakeJob("job-xyz")


class _FakeRetry:
    def __init__(self, max: int, interval: list[int]) -> None:
        self.max = max
        self.interval = interval


def make_fake_queue() -> tuple[_FakeQueue, object]:
    fake_queue = _FakeQueue("transcript", object())

    def fake_queue_ctor(name: str, connection: object) -> _FakeQueue:
        assert name == "transcript"
        return fake_queue

    return fake_queue, fake_queue_ctor


class _FakeRedis:
    @staticmethod
    def from_url(url: str, decode_responses: bool = False):
        assert decode_responses is True
        assert url == "redis://fake"
        return object()


class _FakeSub:
    def __init__(self, *_: object, **__: object) -> None:
        pass

    def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass


@pytest.mark.asyncio
async def test_transcript_cog_stt_enqueues_via_rq_top_level_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Fake rq with only top-level Retry
    fake_queue, fake_queue_ctor = make_fake_queue()
    monkeypatch.setitem(
        __import__("sys").modules,
        "rq",
        SimpleNamespace(Queue=fake_queue_ctor, Retry=_FakeRetry),
    )
    monkeypatch.setitem(__import__("sys").modules, "redis", _FakeRedis)

    monkeypatch.setattr(transcript_mod, "TranscriptEventSubscriber", _FakeSub, raising=True)

    bot = SimpleNamespace()
    cfg = _cfg_stt()
    service = _FakeService()
    cog = TranscriptCog(bot=bot, config=cfg, transcript_service=service)

    inter = _FakeInteraction()
    log = logging.LoggerAdapter(logging.getLogger(__name__), {})
    handled = await cog._handle_stt_request(
        interaction=inter, log=log, url="https://x", req_id="rid-1", user_id=42
    )
    assert handled is True
    assert fake_queue.last_args is not None
    fpath, payload = fake_queue.last_args
    assert fpath == "clubbot.workers.transcript.process_transcript_job"
    assert isinstance(payload, dict)
    assert payload["request_id"] == "rid-1" and payload["user_id"] == 42
