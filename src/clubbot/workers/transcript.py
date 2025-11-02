from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, TypedDict

from ..config import load_config
from ..logging import set_request_id
from ..services.jobs.events import (
    DEFAULT_EVENTS_CHANNEL,
    DEFAULT_RESULT_KEY_PREFIX,
    TranscriptCompletedEvent,
    TranscriptFailedEvent,
    build_result_key,
    encode_event,
)
from ..services.transcript.app import TranscriptService
from ..utils.errors import UserInputError


class TranscriptPayload(TypedDict):
    request_id: str
    url: str
    user_id: int


if TYPE_CHECKING:
    from typing import Protocol as _Protocol

    class _RedisSyncProto(_Protocol):  # pragma: no cover - typing only
        def publish(self, channel: str, message: str) -> int: ...
        def setex(self, key: str, ttl: int, value: str) -> bool: ...

    def _redis_from_url(url: str) -> _RedisSyncProto: ...
else:  # pragma: no cover - runtime import only

    def _redis_from_url(url: str):
        import redis

        return redis.from_url(url, decode_responses=True)


def process_transcript_job(payload: TranscriptPayload) -> None:
    cfg = load_config()
    req = payload["request_id"]
    set_request_id(req)
    logger = logging.getLogger(__name__)

    # Build services
    svc = TranscriptService(cfg)
    url = payload["url"]
    user_id = payload["user_id"]

    redis_url = getattr(cfg, "REDIS_URL", None) or ("")
    if not redis_url:
        raise RuntimeError("REDIS_URL missing for RQ worker")
    conn = _redis_from_url(redis_url)
    channel = getattr(cfg, "TRANSCRIPT_EVENTS_CHANNEL", DEFAULT_EVENTS_CHANNEL)
    prefix = getattr(cfg, "TRANSCRIPT_RESULT_KEY_PREFIX", DEFAULT_RESULT_KEY_PREFIX)

    try:
        # Keep CPU-bound work off the event loop
        res = asyncio.run(asyncio.to_thread(svc.fetch_cleaned, url))
    except UserInputError as e:
        failed: TranscriptFailedEvent = {
            "type": "failed",
            "request_id": req,
            "user_id": user_id,
            "error_kind": "user",
            "message": str(e),
        }
        conn.publish(channel, encode_event(failed))
        logger.info("User error for req=%s: %s", req, e)
        return
    except (RuntimeError, ValueError, TypeError, KeyError, OSError) as e:
        failed_evt: TranscriptFailedEvent = {
            "type": "failed",
            "request_id": req,
            "user_id": user_id,
            "error_kind": "system",
            "message": "system error",
        }
        conn.publish(channel, encode_event(failed_evt))
        logger.exception("Worker error for req=%s: %s", req, e)
        # Re-raise to allow RQ to retry according to policy
        raise

    # Store content and publish completion
    text = res.text
    key = build_result_key(prefix, req)
    ttl = int(getattr(cfg, "RQ_TRANSCRIPT_RESULT_TTL_SEC", 86400))
    conn.setex(key, ttl, text)

    completed: TranscriptCompletedEvent = {
        "type": "completed",
        "request_id": req,
        "user_id": user_id,
        "url": res.url,
        "video_id": res.video_id,
        "content_key": key,
    }
    conn.publish(channel, encode_event(completed))
    logger.info("Transcript done req=%s vid=%s", req, res.video_id)
