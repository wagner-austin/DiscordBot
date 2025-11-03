from __future__ import annotations

from types import SimpleNamespace

import pytest
import src.clubbot.workers.transcript as worker_mod


def test_worker_raises_when_redis_url_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    # Ensure load_config returns an object with REDIS_URL empty
    cfg = SimpleNamespace(
        REDIS_URL="",
        TRANSCRIPT_EVENTS_CHANNEL="x",
        TRANSCRIPT_RESULT_KEY_PREFIX="y",
    )
    monkeypatch.setattr(worker_mod, "load_config", lambda: cfg)
    # Avoid constructing real TranscriptService
    monkeypatch.setattr(worker_mod, "TranscriptService", lambda cfg_obj: object())

    # Process should fail before any Redis interaction
    with pytest.raises(RuntimeError):
        worker_mod.process_transcript_job({"request_id": "r1", "url": "https://x", "user_id": 1})
