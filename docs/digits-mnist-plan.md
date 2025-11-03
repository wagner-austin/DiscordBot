# Handwritten Digits (MNIST) – DiscordBot Integration Plan

Status: planning document only (no code changes in this commit). This proposal aligns with the current DiscordBot codebase (containers, cogs, jobs, logging, typing) and defines deliberate, testable contracts to minimize drift and future tech debt.

Goals
- Highest-accuracy MNIST digit recognition with robust preprocessing for arbitrary PNG/JPG uploads.
- Keep DiscordBot organized and lean at the cog layer; put heavy logic in `services/digits/*`.
- Strong, strict typing (mypy strict), no Any, no casts; explicit contracts and dataclasses.
- Deterministic training artifacts, manifest-driven model selection, and safe hot swaps.
- Reuse existing infra (ServiceContainer, RQ jobs, structured logging, error handling patterns).

Non‑Goals (for this iteration)
- No external inference microservice; the bot hosts inference.
- No alphabet recognition yet (design remains extensible to 36 classes via retraining).

Architecture Overview
- Cog: thin slash command surface, request-scoped logging, rate limiting, and validation.
- Services (digits): preprocessing, model factories, inference, training, artifacts, and jobs.
- Jobs: RQ for training/eval only; inference runs in-process with CPU executor.
- Artifacts: per-model directory with `model.pt`, `manifest.json`, `metrics.json`.
- Manifest: encodes preprocess signature, class count, arch, and metrics; prevents drift.

Codebase Touchpoints (existing)
- Container: `DiscordBot/src/clubbot/container.py` (wires cogs/services via DI).
- Orchestrator: `DiscordBot/src/clubbot/orchestrator.py` (listeners, sync).
- BaseCog: `DiscordBot/src/clubbot/cogs/base.py` (request id/logging helpers).
- Rate limit: `DiscordBot/src/clubbot/utils/rate_limiter.py`.
- Errors: `DiscordBot/src/clubbot/utils/errors.py` (user‑error signaling).
- RQ enqueuer pattern: `DiscordBot/src/clubbot/services/jobs/rq_enqueuer.py`.
- RQ worker pattern + events: `DiscordBot/src/clubbot/workers/transcript.py`,
  `DiscordBot/src/clubbot/services/jobs/events.py`.
- Metrics (QR‑specific today): `DiscordBot/src/clubbot/services/metrics/*`.

Planned Modules (to be added under src/clubbot)
1) `services/digits/preprocess.py`
   - Purpose: robust image normalization for arbitrary uploads, matching MNIST expectations.
   - Types
     - `@dataclass(frozen=True) PreprocessConfig`:
       - `invert_auto: bool` (default true)
       - `center: bool` (default true)
       - `target_size: tuple[int, int]` (default (28, 28))
       - Optional knobs: `thresholding: Literal["adaptive","otsu","none"] = "adaptive"`
     - `@dataclass(frozen=True) PreprocessResult`:
       - `image: "np.ndarray"` (H,W float32, normalized)
       - `visual_png: bytes | None` (optional visualization)
       - `auto_inverted: bool`, `used_component_crop: bool`
   - Contracts
     - `def preprocess_bytes(data: bytes, cfg: PreprocessConfig) -> PreprocessResult`
     - `def visualize_28x28(image: "np.ndarray") -> bytes`
   - Behavior
     - Load via PIL, convert to grayscale; composite alpha on white; strip EXIF.
     - Auto‑invert if background dark (heuristic) unless overridden.
     - Threshold → largest connected component → bbox crop; center by center‑of‑mass.
     - Square pad with margin, resize to 28×28; normalize to MNIST mean/std.
     - Fallback to square pad+resize when no component found; record flags.

2) `services/digits/model.py`
   - Purpose: CNN architectures and a small factory without framework leakage elsewhere.
   - Types
     - `@dataclass(frozen=True) ModelSpec`:
       - `arch: Literal["lenet","deep_cnn"]`
       - `n_classes: int` (default 10)
     - `class DigitNet(Protocol): ...` (predicts logits for N×1×28×28)
   - Contracts
     - `def build_model(spec: ModelSpec) -> "nn.Module"`
     - Arch builders: `build_lenet(n_classes: int)`, `build_deep_cnn(n_classes: int)`
   - Notes: CPU‑friendly, BatchNorm + Dropout; no Any, no casts.

3) `services/digits/artifacts.py`
   - Purpose: manifest and checkpoint I/O; drift prevention.
   - Types
     - `@dataclass(frozen=True) Manifest`:
       - `name: str`, `version: str`, `arch: str`, `n_classes: int`
       - `preprocess_hash: str` (stable from PreprocessConfig)
       - `created_at: str` (ISO 8601)
       - `val_acc: float | None`
       - Optional calibration info (temperature): `calibration_T: float | None`
   - Contracts
     - `def load_manifest(model_dir: str) -> Manifest`
     - `def validate_compat(m: Manifest, spec: ModelSpec, prep_hash: str) -> None`
     - `def model_paths(model_dir: str) -> tuple[str, str, str]` (pt, manifest, metrics)

4) `services/digits/inference.py`
   - Purpose: lazy model loading, thread‑offloaded CPU inference, optional TTA.
   - Types
     - `@dataclass(frozen=True) PredictOptions`:
       - `invert: bool | None`, `center: bool | None`, `visualize: bool = False`, `use_tta: bool = False`
     - `@dataclass(frozen=True) PredictResult`:
       - `digit: int`, `confidence: float`, `probs: tuple[float, ...]`, `visual_png: bytes | None`
   - Contracts
     - `class DigitInference:`
       - `def __init__(self, model_root: str, active_id: str) -> None`
       - `async def ensure_loaded(self) -> None` (guarded by `asyncio.Lock`)
       - `def predict(self, data: bytes, opts: PredictOptions) -> PredictResult`
       - `def hot_reload_if_changed(self) -> None` (mtime/symlink or cfg switch)
   - Behavior
     - Load model once; execute inference in `asyncio.to_thread` from the cog.
     - TTA only when confidence < threshold from config.

5) `services/digits/datasets.py`
   - Purpose: MNIST + ImageFolder loaders with shared transforms.
   - Contracts
     - `def build_mnist_loaders(batch: int, workers: int) -> tuple[DataLoader, DataLoader]`
     - `def build_imagefolder_loaders(root: str, batch: int, workers: int) -> tuple[DataLoader, DataLoader]`

6) `services/digits/training.py`
   - Purpose: deterministic CPU training loop, early stopping, metrics, export.
   - Types
     - `@dataclass(frozen=True) TrainSpec`:
       - `arch: Literal["lenet","deep_cnn"]`, `epochs: int`, `batch: int`, `lr: float`, `augment: bool`
       - `dataset: Literal["mnist","imagefolder"]`, `image_root: str | None`
     - `@dataclass(frozen=True) TrainResult`:
       - `model_id: str`, `best_val_acc: float`, `artifact_dir: str`
   - Contracts
     - `def run_training(spec: TrainSpec, out_root: str) -> TrainResult`
     - Writes: `model.pt`, `manifest.json`, `metrics.json` into `out_root/<model_id>/`.

7) `services/jobs/digits_events.py` (parallel to transcript events)
   - Channel/keys: `digits:events`, `digits:result:`
   - Events
     - `class DigitTrainCompletedEvent(TypedDict)`:
       - `type: Literal["completed"]`, `request_id: str`, `user_id: int`, `model_id: str`, `artifact_dir: str`
     - `class DigitTrainFailedEvent(TypedDict)`:
       - `type: Literal["failed"]`, `request_id: str`, `user_id: int`, `error_kind: Literal["user","system"]`, `message: str`
   - Helpers: `encode_event`, `try_decode_event`, `build_result_key(prefix, request_id)`

8) `services/jobs/digits_enqueuer.py` (parallel to `rq_enqueuer.py`)
   - Contracts
     - `@dataclass(frozen=True) RQDigitsEnqueuer` with fields mirroring transcript enqueuer:
       - `redis_url: str`, `queue_name: str = "digits"`, job/result/failure TTLs, retry policy
     - `def enqueue_train(self, *, request_id: str, user_id: int, spec: TrainSpec) -> str`
       - Enqueues `src.clubbot.workers.digits.process_digit_train_job` with payload

9) `workers/digits.py` (parallel to `workers/transcript.py`)
   - Types
     - `class DigitTrainPayload(TypedDict)`:
       - `request_id: str`, `user_id: int`, `spec: dict` (strictly validated to `TrainSpec` on worker side)
   - Contract
     - `def process_digit_train_job(payload: DigitTrainPayload) -> None`
   - Behavior
     - `cfg = load_config()`; `set_request_id(req)`; build `TrainSpec` safely; run `run_training` using `asyncio.run(asyncio.to_thread(...))` to keep CPU work off event loop.
     - Publish completed/failed events via Redis using `digits_events` definitions.
     - Store a small status record under `digits:result:<req>` with model id/dir for quick lookup (TTL via env).

Cog (planned): `cogs/digits.py`
- Class: `class DigitCog(BaseCog)`
- Commands
  - `/digit predict image:<attachment> invert:<bool?> center:<bool?> visualize:<bool?>`
    - Flow: defer (ephemeral configurable) → validate content type/size → `await asyncio.to_thread(digit_service.predict, bytes, opts)` → send result + optional 28×28 visualization.
  - `/digit info` → report active model id, arch, n_classes, val/test accuracy from manifest.
  - `/digit train epochs:<int> arch:<choice> augment:<bool> dataset:<choice> image_root:<str?>`
    - Flow: enqueue RQ job via `RQDigitsEnqueuer` → return job id and DM on completion.
- Reuse `BaseCog` helpers and the QR cog defer/ack style for resilience.
- Per‑user rate limiting with `RateLimiter` using dedicated digits config values.

Service Container wiring (planned changes)
- `ServiceContainer` (file: `src/clubbot/container.py`)
  - Add `digits_service: DigitService | None = None` (mirrors transcript optionality).
  - In `from_env`: construct `DigitService(cfg)` if `DIGITS_ENABLED`.
  - In `wire_bot_async`: load `DigitCog` if not present and `digits_service` is available.

DigitService (planned): `services/digits/app.py`
- `@dataclass(frozen=True) class DigitService:`
- Fields: `cfg: Config`; `_inference: DigitInference` (init inside `__post_init__`).
- Methods
  - `def predict(self, data: bytes, *, invert: bool | None, center: bool | None, visualize: bool) -> PredictResult`
  - `def active_model_id(self) -> str` (reads from config/symlink; hot‑reload support delegated to inference)
- Logging: `logging.getLogger(__name__)`

Configuration Additions (planned changes to Config and load_config)
- Boolean env parsing must match existing pattern: `"1","true","yes","y","on"`.
- New fields for `Config` (`src/clubbot/config.py`):
  - `DIGITS_ENABLED: bool = True`
  - `DIGITS_PUBLIC_RESPONSES: bool = False`
  - `DIGITS_RATE_LIMIT: int = 2`
  - `DIGITS_RATE_WINDOW_SECONDS: int = 30`
  - `DIGITS_MODEL_DIR: str = "data/digits/models"`
  - `DIGITS_ACTIVE_MODEL: str = "mnist_v1"`
  - `DIGITS_TTA: bool = False`
  - `DIGITS_CONF_THRESHOLD: float = 0.85`
  - `DIGITS_MAX_IMAGE_MB: int = 2`
  - `DIGITS_PREDICT_TIMEOUT_SECONDS: int = 5`
  - RQ settings (mirroring transcript):
    - `RQ_DIGITS_JOB_TIMEOUT_SEC: int = 900`
    - `RQ_DIGITS_RESULT_TTL_SEC: int = 86400`
    - `RQ_DIGITS_FAILURE_TTL_SEC: int = 604800`
    - `RQ_DIGITS_RETRY_MAX: int = 2`
    - `RQ_DIGITS_RETRY_INTERVALS_SEC: tuple[int, int] = (60, 300)`
    - `DIGITS_EVENTS_CHANNEL: str = "digits:events"`
    - `DIGITS_RESULT_KEY_PREFIX: str = "digits:result:"`
- `load_config()` will populate these using existing helpers `_s`, `_i`, `_f` and boolean normalization.

Metrics & Observability (planned, QR metrics remain unchanged)
- Introduce a new metrics writer for digits (separate from QR tables) to avoid schema coupling.
  - File: `services/digits/metrics.py`
  - Counters: predictions total/success/fail, TTA used, low‑confidence triggers, preprocess path (component‑crop vs fallback), bytes/latency histograms.
  - Storage: separate SQLite table (new DB or same file with different tables). Keep a similar interface pattern to `MetricsService` but digits‑specific.
  - All logging goes through `logging.getLogger(__name__)` and `set_request_id` in cog scope.

Error Handling & Validation
- Input validation: content type restrict to `image/png` and `image/jpeg` (strict), max size `DIGITS_MAX_IMAGE_MB`.
- Fail fast user errors via `UserInputError` to reuse `BaseCog.handle_user_error`.
- Timeouts on attachment download and inference via executor with cancellation guard.
- Gracefully handle transparent PNG backgrounds and EXIF orientation.

Concurrency & Performance
- Single process‑wide model instance with `asyncio.Lock` around first load and hot reload.
- Inference runs in `asyncio.to_thread` to avoid blocking the event loop.
- Optional TTA for low confidence: average logits across small rotations; gated by `DIGITS_TTA` and `DIGITS_CONF_THRESHOLD`.

Testing Strategy (mypy strict, pytest)
- Preprocess unit tests: varied aspect ratios, alpha, dark backgrounds, thresholding branches.
- Inference smoke: deterministic softmax ordering with fixed weights; visualization bytes produced.
- Cog tests: slash command validation paths, rate limiting, defer/ack logic, and happy path with a stubbed `DigitService`.
- Worker tests: RQ payload validation, job retries surfaces, event encoding/decoding, TTL keys.
- Manifest integrity tests: mismatch on preprocess or n_classes raises.

Model Swap/Upgrade Procedure (no package juggling)
- Training writes a new `artifacts_dir/<model_id>/` with manifest and metrics.
- Swap active model by updating `DIGITS_ACTIVE_MODEL` or rotating `current` symlink.
- On next request, inference checks active id/mtime and hot‑reloads safely.

Implementation Steps (sequenced, minimal drift)
1) Add config fields + defaults in `src/clubbot/config.py` and parse in `load_config()`.
2) Add `services/digits/*` modules per contracts above.
3) Add `workers/digits.py` and `services/jobs/digits_{events,enqueuer}.py` mirroring transcript patterns.
4) Add `DigitService` and wire in `ServiceContainer.from_env` and `wire_bot_async`.
5) Add `cogs/digits.py` with commands and rate limiting.
6) Tests for preprocessing, inference, cog, workers, and manifest.
7) Baseline training run (LeNet) to produce `mnist_v1` artifact; set as active.
8) Accuracy hardening (augment, calibration, optional TTA) and metrics/reporting.

Colab & Local Training Notes (optional)
- Use TorchVision MNIST with the same preprocessing signature used in inference.
- Export `model.pt`, `manifest.json`, `metrics.json`; copy under `DIGITS_MODEL_DIR`.
- Keep seeds fixed; log metrics to JSON for reproducibility.

Compatibility & Style Guarantees
- No Any, no casts; Protocols and TypedDicts define boundaries.
- Dataclasses are frozen to prevent accidental mutation and aid hashing.
- File structure and DI match current project organization; cog follows `QRCog` defer/ack and error‑handling conventions.
- Config parsing follows current helpers and boolean normalization.
- Logging uses `set_request_id` and BaseCog adapters for consistent correlation.

