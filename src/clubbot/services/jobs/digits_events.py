from __future__ import annotations

import json
from typing import Final, Literal, TypedDict

DEFAULT_DIGITS_EVENTS_CHANNEL: Final[str] = "digits:events"


class DigitsTrainStartedEvent(TypedDict):
    type: Literal["started"]
    request_id: str
    user_id: int
    model_id: str
    total_epochs: int


class DigitsTrainProgressEvent(TypedDict):
    type: Literal["progress"]
    request_id: str
    user_id: int
    model_id: str
    epoch: int
    total_epochs: int
    val_acc: float | None


class DigitsTrainCompletedEvent(TypedDict):
    type: Literal["completed"]
    request_id: str
    user_id: int
    model_id: str
    run_id: str
    val_acc: float


class DigitsTrainFailedEvent(TypedDict):
    type: Literal["failed"]
    request_id: str
    user_id: int
    model_id: str
    error_kind: Literal["user", "system"]
    message: str


Event = (
    DigitsTrainStartedEvent
    | DigitsTrainProgressEvent
    | DigitsTrainCompletedEvent
    | DigitsTrainFailedEvent
)


def encode_event(event: Event) -> str:
    return json.dumps(event, separators=(",", ":"))


def try_decode_event(payload: str) -> Event | None:
    obj = _parse_json_obj(payload)
    if obj is None:
        return None
    typ = obj.get("type")
    if typ == "started":
        req = obj.get("request_id")
        uid = obj.get("user_id")
        mid = obj.get("model_id")
        tot = obj.get("total_epochs")
        if not (
            isinstance(req, str)
            and isinstance(uid, int)
            and isinstance(mid, str)
            and isinstance(tot, int)
        ):
            return None
        req_s: str = req
        uid_i: int = uid
        mid_s: str = mid
        tot_i: int = tot
        out_started: DigitsTrainStartedEvent = {
            "type": "started",
            "request_id": req_s,
            "user_id": uid_i,
            "model_id": mid_s,
            "total_epochs": tot_i,
        }
        return out_started
        return None
    if typ == "progress":
        req, uid, mid = obj.get("request_id"), obj.get("user_id"), obj.get("model_id")
        ep, tot, acc = obj.get("epoch"), obj.get("total_epochs"), obj.get("val_acc")
        acc_ok = (acc is None) or isinstance(acc, float | int)
        if not (
            isinstance(req, str)
            and isinstance(uid, int)
            and isinstance(mid, str)
            and isinstance(ep, int)
            and isinstance(tot, int)
            and acc_ok
        ):
            return None
        req_s2: str = req
        uid_i2: int = uid
        mid_s2: str = mid
        ep_i: int = ep
        tot_i2: int = tot
        vacc = float(acc) if isinstance(acc, float | int) else None
        out_progress: DigitsTrainProgressEvent = {
            "type": "progress",
            "request_id": req_s2,
            "user_id": uid_i2,
            "model_id": mid_s2,
            "epoch": ep_i,
            "total_epochs": tot_i2,
            "val_acc": vacc,
        }
        return out_progress
        return None
    if typ == "completed":
        req, uid = obj.get("request_id"), obj.get("user_id")
        mid, rid = obj.get("model_id"), obj.get("run_id")
        acc = obj.get("val_acc")
        if not (
            isinstance(req, str)
            and isinstance(uid, int)
            and isinstance(mid, str)
            and isinstance(rid, str)
            and isinstance(acc, float | int)
        ):
            return None
        req_s3: str = req
        uid_i3: int = uid
        mid_s3: str = mid
        rid_s: str = rid
        acc_val: float = float(acc)
        out_completed: DigitsTrainCompletedEvent = {
            "type": "completed",
            "request_id": req_s3,
            "user_id": uid_i3,
            "model_id": mid_s3,
            "run_id": rid_s,
            "val_acc": acc_val,
        }
        return out_completed
        return None
    if typ == "failed":
        req, uid, mid = obj.get("request_id"), obj.get("user_id"), obj.get("model_id")
        kind, msg = obj.get("error_kind"), obj.get("message")
        if (
            isinstance(req, str)
            and isinstance(uid, int)
            and isinstance(mid, str)
            and kind in ("user", "system")
            and isinstance(msg, str)
        ):
            error_kind: Literal["user", "system"] = "user" if kind == "user" else "system"
            return {
                "type": "failed",
                "request_id": req,
                "user_id": uid,
                "model_id": mid,
                "error_kind": error_kind,
                "message": msg,
            }
        return None
    return None


def _parse_json_obj(payload: str) -> dict[str, object] | None:
    try:
        obj = json.loads(payload)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    # ensure keys are strings; values are objects
    out: dict[str, object] = {}
    for k, v in obj.items():
        if isinstance(k, str):
            out[k] = v
    return out
