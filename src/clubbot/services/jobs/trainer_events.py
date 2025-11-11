from __future__ import annotations

import json
from typing import Final, Literal, NotRequired, TypedDict

DEFAULT_TRAINER_EVENTS_CHANNEL: Final[str] = "trainer:events"


class StartedV1(TypedDict):
    type: Literal["trainer.train.started.v1"]
    request_id: str
    run_id: str
    user_id: int
    model_family: str
    model_size: str
    total_epochs: int
    queue: str
    cpu_cores: NotRequired[int]
    memory_mb: NotRequired[int]
    optimal_threads: NotRequired[int]
    optimal_workers: NotRequired[int]
    batch_size: NotRequired[int]
    learning_rate: NotRequired[float]


class ProgressV1(TypedDict):
    type: Literal["trainer.train.progress.v1"]
    request_id: str
    run_id: str
    user_id: int
    epoch: int
    total_epochs: int
    step: int
    loss: float


class CompletedV1(TypedDict):
    type: Literal["trainer.train.completed.v1"]
    request_id: str
    run_id: str
    user_id: int
    loss: float
    perplexity: float
    artifact_path: str


class FailedV1(TypedDict):
    type: Literal["trainer.train.failed.v1"]
    request_id: str
    run_id: str
    user_id: int
    error_kind: Literal["user", "system"]
    message: str
    status: Literal["failed", "canceled"]


Event = StartedV1 | ProgressV1 | CompletedV1 | FailedV1


def encode_event(ev: Event) -> str:
    return json.dumps(ev, separators=(",", ":"))


def _decode_started(obj: dict[str, object]) -> StartedV1 | None:
    req = obj.get("request_id")
    rid = obj.get("run_id")
    uid = obj.get("user_id")
    fam = obj.get("model_family")
    siz = obj.get("model_size")
    te = obj.get("total_epochs")
    q = obj.get("queue")
    if (
        isinstance(req, str)
        and isinstance(rid, str)
        and isinstance(uid, int)
        and isinstance(fam, str)
        and isinstance(siz, str)
        and isinstance(te, int)
        and isinstance(q, str)
    ):
        out: StartedV1 = {
            "type": "trainer.train.started.v1",
            "request_id": req,
            "run_id": rid,
            "user_id": uid,
            "model_family": fam,
            "model_size": siz,
            "total_epochs": te,
            "queue": q,
        }
        # Optional numeric fields
        for k in ("cpu_cores", "memory_mb", "optimal_threads", "optimal_workers", "batch_size"):
            v = obj.get(k)
            if isinstance(v, int):
                out[k] = v
        v2 = obj.get("learning_rate")
        if isinstance(v2, float | int):
            out["learning_rate"] = float(v2)
        return out
    return None


def _decode_progress(obj: dict[str, object]) -> ProgressV1 | None:
    req = obj.get("request_id")
    rid = obj.get("run_id")
    uid = obj.get("user_id")
    ep = obj.get("epoch")
    te = obj.get("total_epochs")
    st = obj.get("step")
    ls = obj.get("loss")
    if (
        isinstance(req, str)
        and isinstance(rid, str)
        and isinstance(uid, int)
        and isinstance(ep, int)
        and isinstance(te, int)
        and isinstance(st, int)
        and isinstance(ls, int | float)
    ):
        return {
            "type": "trainer.train.progress.v1",
            "request_id": req,
            "run_id": rid,
            "user_id": uid,
            "epoch": ep,
            "total_epochs": te,
            "step": st,
            "loss": float(ls),
        }
    return None


def _decode_completed(obj: dict[str, object]) -> CompletedV1 | None:
    req = obj.get("request_id")
    rid = obj.get("run_id")
    uid = obj.get("user_id")
    loss = obj.get("loss")
    ppl = obj.get("perplexity")
    art = obj.get("artifact_path")
    if (
        isinstance(req, str)
        and isinstance(rid, str)
        and isinstance(uid, int)
        and isinstance(loss, int | float)
        and isinstance(ppl, int | float)
        and isinstance(art, str)
    ):
        return {
            "type": "trainer.train.completed.v1",
            "request_id": req,
            "run_id": rid,
            "user_id": uid,
            "loss": float(loss),
            "perplexity": float(ppl),
            "artifact_path": art,
        }
    return None


def _decode_failed(obj: dict[str, object]) -> FailedV1 | None:
    req = obj.get("request_id")
    rid = obj.get("run_id")
    uid = obj.get("user_id")
    kind = obj.get("error_kind")
    msg = obj.get("message")
    st = obj.get("status")
    if (
        isinstance(req, str)
        and isinstance(rid, str)
        and isinstance(uid, int)
        and kind in ("user", "system")
        and isinstance(msg, str)
        and st in ("failed", "canceled")
    ):
        return {
            "type": "trainer.train.failed.v1",
            "request_id": req,
            "run_id": rid,
            "user_id": uid,
            "error_kind": ("user" if kind == "user" else "system"),
            "message": msg,
            "status": ("canceled" if st == "canceled" else "failed"),
        }
    return None


def try_decode_event(payload: str) -> Event | None:
    try:
        raw: object = json.loads(payload)
    except json.JSONDecodeError:
        return None
    if not isinstance(raw, dict):
        return None
    typ = raw.get("type")
    if typ == "trainer.train.started.v1":
        return _decode_started(raw)
    if typ == "trainer.train.progress.v1":
        return _decode_progress(raw)
    if typ == "trainer.train.completed.v1":
        return _decode_completed(raw)
    if typ == "trainer.train.failed.v1":
        return _decode_failed(raw)
    return None
