from __future__ import annotations

import json
from typing import Final, Literal, NotRequired, TypedDict

DEFAULT_DIGITS_EVENTS_CHANNEL: Final[str] = "digits:events"


class StartedV1(TypedDict):
    type: Literal["digits.train.started.v1"]
    request_id: str
    user_id: int
    model_id: str
    run_id: str | None
    ts: str
    total_epochs: int
    queue: str
    # Optional rich context (if provided by producer)
    cpu_cores: NotRequired[int]
    optimal_threads: NotRequired[int]
    memory_mb: NotRequired[int]
    optimal_workers: NotRequired[int]
    max_batch_size: NotRequired[int]
    device: NotRequired[str]
    batch_size: NotRequired[int]
    learning_rate: NotRequired[float]
    augment: NotRequired[bool]
    aug_rotate: NotRequired[float]
    aug_translate: NotRequired[float]
    noise_prob: NotRequired[float]
    dots_prob: NotRequired[float]


class BatchV1(TypedDict):
    type: Literal["digits.train.batch.v1"]
    request_id: str
    user_id: int
    model_id: str
    run_id: str | None
    ts: str
    epoch: int
    total_epochs: int
    batch: int
    total_batches: int
    batch_loss: float
    batch_acc: float
    avg_loss: float
    samples_per_sec: float
    # Memory metrics (from cgroup-aware monitoring)
    main_rss_mb: int
    workers_rss_mb: int
    worker_count: int
    cgroup_usage_mb: int
    cgroup_limit_mb: int
    cgroup_pct: float
    anon_mb: int
    file_mb: int


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


class BestV1(TypedDict):
    type: Literal["digits.train.best.v1"]
    request_id: str
    user_id: int
    model_id: str
    run_id: str | None
    ts: str
    epoch: int
    val_acc: float


class ArtifactV1(TypedDict):
    type: Literal["digits.train.artifact.v1"]
    request_id: str
    user_id: int
    model_id: str
    run_id: str | None
    ts: str
    path: str


class UploadV1(TypedDict):
    type: Literal["digits.train.upload.v1"]
    request_id: str
    user_id: int
    model_id: str
    run_id: str | None
    ts: str
    status: int
    model_bytes: int
    manifest_bytes: int


class PruneV1(TypedDict):
    type: Literal["digits.train.prune.v1"]
    request_id: str
    user_id: int
    model_id: str
    run_id: str | None
    ts: str
    deleted_count: int


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
    queue: str
    status: Literal["failed", "canceled"]


EventV1 = (
    StartedV1
    | BatchV1
    | EpochV1
    | BestV1
    | ArtifactV1
    | UploadV1
    | PruneV1
    | CompletedV1
    | FailedV1
)


def encode_event(event: EventV1) -> str:
    return json.dumps(event, separators=(",", ":"))


def try_decode_event(payload: str) -> EventV1 | None:
    obj = _parse_json_obj(payload)
    if obj is None:
        return None
    typ = obj.get("type")
    from collections.abc import Callable as _Callable

    handlers: dict[str, _Callable[[dict[str, object]], EventV1 | None]] = {
        "digits.train.started.v1": _decode_started,
        "digits.train.batch.v1": _decode_batch,
        "digits.train.epoch.v1": _decode_epoch,
        "digits.train.best.v1": _decode_best,
        "digits.train.artifact.v1": _decode_artifact,
        "digits.train.upload.v1": _decode_upload,
        "digits.train.prune.v1": _decode_prune,
        "digits.train.completed.v1": _decode_completed,
        "digits.train.failed.v1": _decode_failed,
    }
    if isinstance(typ, str):
        func = handlers.get(typ)
        if func is not None:
            return func(obj)
    return None


def _attach_optional_context(out_st: StartedV1, src: dict[str, object]) -> None:
    cpu = src.get("cpu_cores")
    if isinstance(cpu, int):
        out_st["cpu_cores"] = cpu
    thr = src.get("optimal_threads")
    if isinstance(thr, int):
        out_st["optimal_threads"] = thr
    mem = src.get("memory_mb")
    if isinstance(mem, int):
        out_st["memory_mb"] = mem
    w = src.get("optimal_workers")
    if isinstance(w, int):
        out_st["optimal_workers"] = w
    mbs = src.get("max_batch_size")
    if isinstance(mbs, int):
        out_st["max_batch_size"] = mbs
    dev = src.get("device")
    if isinstance(dev, str):
        out_st["device"] = dev


def _attach_optional_augment(out_st: StartedV1, src: dict[str, object]) -> None:
    bs = src.get("batch_size")
    if isinstance(bs, int):
        out_st["batch_size"] = bs
    lr = src.get("learning_rate")
    if isinstance(lr, int | float):
        out_st["learning_rate"] = float(lr)
    aug = src.get("augment")
    if isinstance(aug, bool):
        out_st["augment"] = aug
    ar = src.get("aug_rotate")
    if isinstance(ar, int | float):
        out_st["aug_rotate"] = float(ar)
    at = src.get("aug_translate")
    if isinstance(at, int | float):
        out_st["aug_translate"] = float(at)
    npv = src.get("noise_prob")
    if isinstance(npv, int | float):
        out_st["noise_prob"] = float(npv)
    dpv = src.get("dots_prob")
    if isinstance(dpv, int | float):
        out_st["dots_prob"] = float(dpv)


def _decode_started(obj: dict[str, object]) -> StartedV1 | None:
    req = obj.get("request_id")
    uid = obj.get("user_id")
    mid = obj.get("model_id")
    tot = obj.get("total_epochs")
    ts = obj.get("ts")
    run = obj.get("run_id")
    queue = obj.get("queue")
    if (
        isinstance(req, str)
        and isinstance(uid, int)
        and isinstance(mid, str)
        and isinstance(tot, int)
        and isinstance(ts, str)
        and (run is None or isinstance(run, str))
        and isinstance(queue, str)
    ):
        out_st: StartedV1 = {
            "type": "digits.train.started.v1",
            "request_id": req,
            "user_id": uid,
            "model_id": mid,
            "run_id": run if isinstance(run, str) else None,
            "ts": ts,
            "total_epochs": tot,
            "queue": queue,
        }
        _attach_optional_context(out_st, obj)
        _attach_optional_augment(out_st, obj)
        return out_st
    return None


def _decode_batch(obj: dict[str, object]) -> BatchV1 | None:
    req, uid, mid = obj.get("request_id"), obj.get("user_id"), obj.get("model_id")
    ep, tot = obj.get("epoch"), obj.get("total_epochs")
    bat, tot_bat = obj.get("batch"), obj.get("total_batches")
    bl, ba = obj.get("batch_loss"), obj.get("batch_acc")
    al, sps = obj.get("avg_loss"), obj.get("samples_per_sec")
    ts, run = obj.get("ts"), obj.get("run_id")
    # Memory metrics (cgroup-aware monitoring)
    main_rss = obj.get("main_rss_mb")
    workers_rss = obj.get("workers_rss_mb")
    worker_cnt = obj.get("worker_count")
    cgroup_usage = obj.get("cgroup_usage_mb")
    cgroup_limit = obj.get("cgroup_limit_mb")
    cgroup_pct = obj.get("cgroup_pct")
    anon = obj.get("anon_mb")
    file = obj.get("file_mb")
    if (
        isinstance(req, str)
        and isinstance(uid, int)
        and isinstance(mid, str)
        and isinstance(ep, int)
        and isinstance(tot, int)
        and isinstance(bat, int)
        and isinstance(tot_bat, int)
        and isinstance(bl, float | int)
        and isinstance(ba, float | int)
        and isinstance(al, float | int)
        and isinstance(sps, float | int)
        and isinstance(ts, str)
        and (run is None or isinstance(run, str))
        and isinstance(main_rss, int)
        and isinstance(workers_rss, int)
        and isinstance(worker_cnt, int)
        and isinstance(cgroup_usage, int)
        and isinstance(cgroup_limit, int)
        and isinstance(cgroup_pct, float | int)
        and isinstance(anon, int)
        and isinstance(file, int)
    ):
        out_b: BatchV1 = {
            "type": "digits.train.batch.v1",
            "request_id": req,
            "user_id": uid,
            "model_id": mid,
            "run_id": run if isinstance(run, str) else None,
            "ts": ts,
            "epoch": ep,
            "total_epochs": tot,
            "batch": bat,
            "total_batches": tot_bat,
            "batch_loss": float(bl),
            "batch_acc": float(ba),
            "avg_loss": float(al),
            "samples_per_sec": float(sps),
            "main_rss_mb": main_rss,
            "workers_rss_mb": workers_rss,
            "worker_count": worker_cnt,
            "cgroup_usage_mb": cgroup_usage,
            "cgroup_limit_mb": cgroup_limit,
            "cgroup_pct": float(cgroup_pct),
            "anon_mb": anon,
            "file_mb": file,
        }
        return out_b
    return None


def _decode_epoch(obj: dict[str, object]) -> EpochV1 | None:
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


def _decode_best(obj: dict[str, object]) -> BestV1 | None:
    req, uid, mid = obj.get("request_id"), obj.get("user_id"), obj.get("model_id")
    ep, acc = obj.get("epoch"), obj.get("val_acc")
    ts, run = obj.get("ts"), obj.get("run_id")
    if (
        isinstance(req, str)
        and isinstance(uid, int)
        and isinstance(mid, str)
        and isinstance(ep, int)
        and isinstance(acc, float | int)
        and isinstance(ts, str)
        and (run is None or isinstance(run, str))
    ):
        out_best: BestV1 = {
            "type": "digits.train.best.v1",
            "request_id": req,
            "user_id": uid,
            "model_id": mid,
            "run_id": run if isinstance(run, str) else None,
            "ts": ts,
            "epoch": ep,
            "val_acc": float(acc),
        }
        return out_best
    return None


def _decode_artifact(obj: dict[str, object]) -> ArtifactV1 | None:
    req, uid, mid = obj.get("request_id"), obj.get("user_id"), obj.get("model_id")
    path, ts, run = obj.get("path"), obj.get("ts"), obj.get("run_id")
    if (
        isinstance(req, str)
        and isinstance(uid, int)
        and isinstance(mid, str)
        and isinstance(path, str)
        and isinstance(ts, str)
        and (run is None or isinstance(run, str))
    ):
        out_art: ArtifactV1 = {
            "type": "digits.train.artifact.v1",
            "request_id": req,
            "user_id": uid,
            "model_id": mid,
            "run_id": run if isinstance(run, str) else None,
            "ts": ts,
            "path": path,
        }
        return out_art
    return None


def _decode_upload(obj: dict[str, object]) -> UploadV1 | None:
    req, uid, mid = obj.get("request_id"), obj.get("user_id"), obj.get("model_id")
    status, mb, mfb = obj.get("status"), obj.get("model_bytes"), obj.get("manifest_bytes")
    ts, run = obj.get("ts"), obj.get("run_id")
    if (
        isinstance(req, str)
        and isinstance(uid, int)
        and isinstance(mid, str)
        and isinstance(status, int)
        and isinstance(mb, int)
        and isinstance(mfb, int)
        and isinstance(ts, str)
        and (run is None or isinstance(run, str))
    ):
        out_up: UploadV1 = {
            "type": "digits.train.upload.v1",
            "request_id": req,
            "user_id": uid,
            "model_id": mid,
            "run_id": run if isinstance(run, str) else None,
            "ts": ts,
            "status": status,
            "model_bytes": mb,
            "manifest_bytes": mfb,
        }
        return out_up
    return None


def _decode_prune(obj: dict[str, object]) -> PruneV1 | None:
    req, uid, mid = obj.get("request_id"), obj.get("user_id"), obj.get("model_id")
    count, ts, run = obj.get("deleted_count"), obj.get("ts"), obj.get("run_id")
    if (
        isinstance(req, str)
        and isinstance(uid, int)
        and isinstance(mid, str)
        and isinstance(count, int)
        and isinstance(ts, str)
        and (run is None or isinstance(run, str))
    ):
        out_pr: PruneV1 = {
            "type": "digits.train.prune.v1",
            "request_id": req,
            "user_id": uid,
            "model_id": mid,
            "run_id": run if isinstance(run, str) else None,
            "ts": ts,
            "deleted_count": count,
        }
        return out_pr
    return None


def _decode_completed(obj: dict[str, object]) -> CompletedV1 | None:
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


def _decode_failed(obj: dict[str, object]) -> FailedV1 | None:
    req, uid, mid = obj.get("request_id"), obj.get("user_id"), obj.get("model_id")
    kind, msg, ts = obj.get("error_kind"), obj.get("message"), obj.get("ts")
    run = obj.get("run_id")
    queue = obj.get("queue")
    status = obj.get("status")
    if (
        isinstance(req, str)
        and isinstance(uid, int)
        and isinstance(mid, str)
        and (kind in ("user", "system"))
        and isinstance(msg, str)
        and isinstance(ts, str)
        and (run is None or isinstance(run, str))
        and isinstance(queue, str)
        and (status in ("failed", "canceled"))
    ):
        error_kind: Literal["user", "system"] = "user" if kind == "user" else "system"
        job_status: Literal["failed", "canceled"] = "failed" if status == "failed" else "canceled"
        out_f: FailedV1 = {
            "type": "digits.train.failed.v1",
            "request_id": req,
            "user_id": uid,
            "model_id": mid,
            "run_id": run if isinstance(run, str) else None,
            "ts": ts,
            "error_kind": error_kind,
            "message": msg,
            "queue": queue,
            "status": job_status,
        }
        return out_f
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
