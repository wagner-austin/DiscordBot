from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
import src.clubbot.workers.transcript as worker_mod


class _FakeRedisConn:
    def __init__(self) -> None:
        self.setex_calls: list[tuple[str, int, str]] = []
        self.published: list[tuple[str, str]] = []

    def setex(self, key: str, ttl: int, value: str) -> bool:
        self.setex_calls.append((key, ttl, value))
        return True

    def publish(self, channel: str, payload: str) -> int:
        self.published.append((channel, payload))
        return 1


def _fake_from_url(_url: str, *, decode_responses: bool = False) -> _FakeRedisConn:
    assert decode_responses is True
    return _FakeRedisConn()


class _FakeResult:
    def __init__(self, url: str, vid: str, text: str) -> None:
        self.url = url
        self.video_id = vid
        self.text = text


class _FakeTranscriptService:
    def __init__(self, *_: object, **__: object) -> None:
        self._res: _FakeResult | None = None
        self._err: Exception | None = None

    def set_result(self, r: _FakeResult) -> None:
        self._res = r

    def set_error(self, e: Exception) -> None:
        self._err = e

    def fetch_cleaned(self, url: str) -> _FakeResult:
        if self._err is not None:
            raise self._err
        assert self._res is not None
        return self._res


@pytest.mark.parametrize("kind", ["completed", "failed-user"])
def test_worker_publishes_events_and_sets_content(
    monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    # Redis
    conn = _FakeRedisConn()
    monkeypatch.setitem(
        __import__("sys").modules,
        "redis",
        SimpleNamespace(from_url=lambda url, decode_responses=False: conn),
    )

    # Config
    fake_cfg = SimpleNamespace(
        REDIS_URL="redis://fake",
        RQ_TRANSCRIPT_RESULT_TTL_SEC=111,
        TRANSCRIPT_EVENTS_CHANNEL="transcript:events",
        TRANSCRIPT_RESULT_KEY_PREFIX="transcript:result:",
        # Unused in test
        OPENAI_API_KEY="x",
        TRANSCRIPT_PROVIDER="stt",
    )
    monkeypatch.setattr(worker_mod, "load_config", lambda: fake_cfg)

    # Transcript service
    svc = _FakeTranscriptService()
    if kind == "completed":
        svc.set_result(_FakeResult("https://v", "vid123", "hello world"))
    else:
        from src.clubbot.utils.errors import UserInputError

        svc.set_error(UserInputError("bad input"))
    monkeypatch.setattr(worker_mod, "TranscriptService", lambda cfg: svc)

    payload = {"request_id": "r1", "url": "https://v", "user_id": 7}

    if kind == "completed":
        worker_mod.process_transcript_job(payload)
        # One setex and one publish
        assert conn.setex_calls and conn.published
        ch, msg = conn.published[-1]
        obj = json.loads(msg)
        assert obj["type"] == "completed" and obj["request_id"] == "r1"
        # Content key is set and contains text
        key, ttl, value = conn.setex_calls[-1]
        assert key.endswith("r1") and ttl == 111 and value == "hello world"
    else:
        worker_mod.process_transcript_job(payload)
        # No setex; one publish with failed event
        assert not conn.setex_calls and conn.published
        ch, msg = conn.published[-1]
        obj = json.loads(msg)
        assert obj["type"] == "failed" and obj["error_kind"] == "user"


def test_worker_publishes_failed_system_and_reraises(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.clubbot.workers.transcript as worker_mod

    # Redis
    conn = _FakeRedisConn()
    monkeypatch.setitem(
        __import__("sys").modules,
        "redis",
        SimpleNamespace(from_url=lambda url, decode_responses=False: conn),
    )

    # Config
    fake_cfg = SimpleNamespace(
        REDIS_URL="redis://fake",
        RQ_TRANSCRIPT_RESULT_TTL_SEC=111,
        TRANSCRIPT_EVENTS_CHANNEL="transcript:events",
        TRANSCRIPT_RESULT_KEY_PREFIX="transcript:result:",
        OPENAI_API_KEY="x",
        TRANSCRIPT_PROVIDER="stt",
    )
    monkeypatch.setattr(worker_mod, "load_config", lambda: fake_cfg)

    # Service that raises a system error
    svc = _FakeTranscriptService()
    svc.set_error(RuntimeError("boom"))
    monkeypatch.setattr(worker_mod, "TranscriptService", lambda cfg: svc)

    payload = {"request_id": "r1", "url": "https://v", "user_id": 7}
    with pytest.raises(RuntimeError):
        worker_mod.process_transcript_job(payload)
    # Published failed event with system kind; no setex
    assert not conn.setex_calls and conn.published
    ch, msg = conn.published[-1]
    obj = json.loads(msg)
    assert obj["type"] == "failed" and obj["error_kind"] == "system"
