from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import httpx

from ...utils.correlation import add_correlation_header


@dataclass(frozen=True)
class TrainResponse:
    run_id: str
    job_id: str


@dataclass(frozen=True)
class RunStatus:
    run_id: str
    status: str
    last_heartbeat_ts: float | None
    message: str | None


class ModelTrainerAPIError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = int(status)


class ModelTrainerClient(Protocol):
    async def train(
        self,
        *,
        user_id: int,
        model_family: str,
        model_size: str,
        max_seq_len: int,
        num_epochs: int,
        batch_size: int,
        learning_rate: float,
        corpus_path: str,
        tokenizer_id: str,
        request_id: str,
    ) -> TrainResponse: ...

    async def status(self, *, run_id: str, request_id: str) -> RunStatus: ...


class HTTPModelTrainerClient(ModelTrainerClient):
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None,
        timeout_seconds: int = 10,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._api_key = (api_key or "").strip() or None
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(float(timeout_seconds)))

    async def aclose(self) -> None:
        await self._client.aclose()

    async def train(
        self,
        *,
        user_id: int,
        model_family: str,
        model_size: str,
        max_seq_len: int,
        num_epochs: int,
        batch_size: int,
        learning_rate: float,
        corpus_path: str,
        tokenizer_id: str,
        request_id: str,
    ) -> TrainResponse:
        url = f"{self._base}/runs/train"
        headers: dict[str, str] = {"Accept": "application/json"}
        headers = add_correlation_header(headers, request_id)
        if self._api_key:
            headers["X-Api-Key"] = self._api_key
        body: dict[str, object] = {
            "model_family": model_family,
            "model_size": model_size,
            "max_seq_len": int(max_seq_len),
            "num_epochs": int(num_epochs),
            "batch_size": int(batch_size),
            "learning_rate": float(learning_rate),
            "corpus_path": corpus_path,
            "tokenizer_id": tokenizer_id,
            "user_id": int(user_id),
        }
        try:
            resp = await self._client.post(url, headers=headers, json=body)
        except httpx.RequestError as e:
            raise ModelTrainerAPIError(502, f"Service unavailable: {e}") from e
        if resp.status_code >= 400:
            raise ModelTrainerAPIError(int(resp.status_code), _extract_message(resp))
        try:
            obj: object = resp.json()
            if not isinstance(obj, dict):
                raise ValueError
            run_id = str(obj.get("run_id"))
            job_id = str(obj.get("job_id"))
            return TrainResponse(run_id=run_id, job_id=job_id)
        except (ValueError, TypeError) as e:
            raise ModelTrainerAPIError(500, "Invalid response body") from e

    async def status(self, *, run_id: str, request_id: str) -> RunStatus:
        url = f"{self._base}/runs/{run_id}"
        headers: dict[str, str] = {"Accept": "application/json"}
        headers = add_correlation_header(headers, request_id)
        if self._api_key:
            headers["X-Api-Key"] = self._api_key
        try:
            resp = await self._client.get(url, headers=headers)
        except httpx.RequestError as e:
            raise ModelTrainerAPIError(502, f"Service unavailable: {e}") from e
        if resp.status_code >= 400:
            raise ModelTrainerAPIError(int(resp.status_code), _extract_message(resp))
        obj: object = resp.json()
        if not isinstance(obj, dict):
            raise ModelTrainerAPIError(500, "Invalid response body")
        last = obj.get("last_heartbeat_ts")
        lh = float(last) if isinstance(last, int | float | str) else None
        msg_v = obj.get("message")
        msg = str(msg_v) if isinstance(msg_v, str) else None
        return RunStatus(
            run_id=str(obj.get("run_id")),
            status=str(obj.get("status")),
            last_heartbeat_ts=lh,
            message=msg,
        )


def _extract_message(resp: httpx.Response) -> str:
    try:
        obj: object = resp.json()
        if isinstance(obj, dict):
            raw = obj.get("message") or obj.get("detail") or obj.get("error")
            if isinstance(raw, str) and raw.strip() != "":
                return raw
    except (ValueError, TypeError):
        pass
    return f"HTTP {int(resp.status_code)}"
