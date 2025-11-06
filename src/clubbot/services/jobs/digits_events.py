from __future__ import annotations

import json
from typing import Final, Literal, TypedDict, NotRequired

DEFAULT_DIGITS_EVENTS_CHANNEL: Final[str] = "digits:events"


class StartedV1(TypedDict):
    type: Literal["digits.train.started.v1"]
    request_id: str
    user_id: int
    model_id: str
    run_id: str | None
    ts: str
    total_epochs: int
    # Optional rich context (if provided by producer)
    cpu_cores: NotRequired[int]
    optimal_threads: NotRequired[int]
    optimal_workers: NotRequired[int]
    max_batch_size: NotRequired[int]
    device: NotRequired[str]


class EpochV1(TypedDict):
    type: Literal["digits.train.epoch.v1"]
    request_id: str
    user_id: int
    model_id: str
    run_id: str | None
    ts: str
    epoch: int
    total_epochs: int
    train_loss: float
    val_acc: float
    time_s: float


class CompletedV1(TypedDict):
    type: Literal["digits.train.completed.v1"]
    request_id: str
    user_id: int
    model_id: str
    run_id: str | None
    ts: str
    val_acc: float


class FailedV1(TypedDict):
    type: Literal["digits.train.failed.v1"]
    request_id: str
    user_id: int
    model_id: str
    run_id: str | None
    ts: str
    error_kind: Literal["user", "system"]
    message: str


EventV1 = StartedV1 | EpochV1 | CompletedV1 | FailedV1


def encode_event(event: EventV1) -> str:
    return json.dumps(event, separators=(",", ":"))


def try_decode_event(payload: str) -> EventV1 | None:
    obj = _parse_json_obj(payload)
    if obj is None:
        return None
    typ = obj.get("type")
    if typ == "digits.train.started.v1":
        req = obj.get("request_id")
        uid = obj.get("user_id")
        mid = obj.get("model_id")
        tot = obj.get("total_epochs")
        ts = obj.get("ts")
        run = obj.get("run_id")
        if (
            isinstance(req, str)
            and isinstance(uid, int)
            and isinstance(mid, str)
            and isinstance(tot, int)
            and isinstance(ts, str)
            and (run is None or isinstance(run, str))
        ):
            out_st: StartedV1 = {
                "type": "digits.train.started.v1",
                "request_id": req,
                "user_id": uid,
                "model_id": mid,
                "run_id": run if isinstance(run, str) else None,
                "ts": ts,
                "total_epochs": tot,
            }
            # Optional extras
            cpu = obj.get("cpu_cores")
            if isinstance(cpu, int):
                out_st["cpu_cores"] = cpu
            thr = obj.get("optimal_threads")
            if isinstance(thr, int):
                out_st["optimal_threads"] = thr
            w = obj.get("optimal_workers")
            if isinstance(w, int):
                out_st["optimal_workers"] = w
            bs = obj.get("max_batch_size")
            if isinstance(bs, int):
                out_st["max_batch_size"] = bs
            dev = obj.get("device")
            if isinstance(dev, str):
                out_st["device"] = dev
            return out_st
        return None
    if typ == "digits.train.epoch.v1":
        req, uid, mid = obj.get("request_id"), obj.get("user_id"), obj.get("model_id")
        ep, tot = obj.get("epoch"), obj.get("total_epochs")
        tr, va, ts = obj.get("train_loss"), obj.get("val_acc"), obj.get("ts")
        run = obj.get("run_id")
        if (
            isinstance(req, str)
            and isinstance(uid, int)
            and isinstance(mid, str)
            and isinstance(ep, int)
            and isinstance(tot, int)
            and isinstance(tr, float | int)
            and isinstance(va, float | int)
            and isinstance(ts, str)
            and (run is None or isinstance(run, str))
        ):
            ts_val = obj.get("time_s")
            time_s_val = float(ts_val) if isinstance(ts_val, float | int) else 0.0
            out_ep: EpochV1 = {
                "type": "digits.train.epoch.v1",
                "request_id": req,
                "user_id": uid,
                "model_id": mid,
                "run_id": run if isinstance(run, str) else None,
                "ts": ts,
                "epoch": ep,
                "total_epochs": tot,
                "train_loss": float(tr),
                "val_acc": float(va),
                "time_s": time_s_val,
            }
            return out_ep
        return None
    if typ == "digits.train.completed.v1":
        req, uid = obj.get("request_id"), obj.get("user_id")
        mid, rid = obj.get("model_id"), obj.get("run_id")
        acc, ts = obj.get("val_acc"), obj.get("ts")
        if (
            isinstance(req, str)
            and isinstance(uid, int)
            and isinstance(mid, str)
            and (rid is None or isinstance(rid, str))
            and isinstance(acc, float | int)
            and isinstance(ts, str)
        ):
            out_c: CompletedV1 = {
                "type": "digits.train.completed.v1",
                "request_id": req,
                "user_id": uid,
                "model_id": mid,
                "run_id": rid if isinstance(rid, str) else None,
                "ts": ts,
                "val_acc": float(acc),
            }
            return out_c
        return None
    if typ == "digits.train.failed.v1":
        req, uid, mid = obj.get("request_id"), obj.get("user_id"), obj.get("model_id")
        kind, msg, ts = obj.get("error_kind"), obj.get("message"), obj.get("ts")
        run = obj.get("run_id")
        if (
            isinstance(req, str)
            and isinstance(uid, int)
            and isinstance(mid, str)
            and (kind in ("user", "system"))
            and isinstance(msg, str)
            and isinstance(ts, str)
            and (run is None or isinstance(run, str))
        ):
            error_kind: Literal["user", "system"] = "user" if kind == "user" else "system"
            out_f: FailedV1 = {
                "type": "digits.train.failed.v1",
                "request_id": req,
                "user_id": uid,
                "model_id": mid,
                "run_id": run if isinstance(run, str) else None,
                "ts": ts,
                "error_kind": error_kind,
                "message": msg,
            }
            return out_f
        return None
    return None


def _parse_json_obj(payload: str) -> dict[str, object] | None:
    try:
        obj = json.loads(payload)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    out: dict[str, object] = {}
    for k, v in obj.items():
        if isinstance(k, str):
            out[k] = v
    return out
