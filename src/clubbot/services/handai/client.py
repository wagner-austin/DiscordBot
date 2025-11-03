from __future__ import annotations

import asyncio
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

import httpx

from ...utils.correlation import add_correlation_header


@dataclass(frozen=True)
class PredictResult:
    digit: int
    confidence: float
    probs: tuple[float, ...]
    model_id: str
    uncertain: bool
    latency_ms: int


class HandwritingAPIError(Exception):
    def __init__(
        self,
        status: int,
        message: str,
        *,
        code: str | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status = int(status)
        self.code = code
        self.request_id = request_id


class HandwritingReader(Protocol):
    async def read_digit(
        self,
        *,
        data: bytes,
        filename: str,
        content_type: str,
        request_id: str,
        center: bool,
        visualize: bool,
    ) -> PredictResult: ...


def _top_k_indices(probs: Iterable[float], k: int = 3) -> list[int]:
    xs = list(enumerate(float(p) for p in probs))
    xs.sort(key=lambda kv: kv[1], reverse=True)
    return [xs[i][0] for i in range(min(k, len(xs)))]


class HandwritingClient(HandwritingReader):
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None,
        timeout_seconds: int = 5,
        max_retries: int = 1,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base: str = base_url.rstrip("/")
        self._api_key: str | None = (api_key or "").strip() or None
        self._timeout: float = float(timeout_seconds)
        self._retries: int = max(0, int(max_retries))
        self._client: httpx.AsyncClient = client or httpx.AsyncClient(
            timeout=httpx.Timeout(self._timeout)
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def read_digit(
        self,
        *,
        data: bytes,
        filename: str,
        content_type: str,
        request_id: str,
        center: bool = True,
        visualize: bool = False,
    ) -> PredictResult:
        url = (
            f"{self._base}/v1/read?center={'true' if center else 'false'}"
            f"&visualize={'true' if visualize else 'false'}"
        )
        headers: dict[str, str] = add_correlation_header({"Accept": "application/json"}, request_id)
        if self._api_key:
            headers["X-Api-Key"] = self._api_key
        files: dict[str, tuple[str, bytes, str]] = {"file": (filename, data, content_type)}

        for attempt in range(self._retries + 1):
            try:
                return await self._attempt_read(url, headers, files)
            except httpx.TimeoutException as e:
                if attempt < self._retries:
                    await asyncio.sleep(1.0)
                    continue
                msg = "Timeout calling handwriting service"
                raise HandwritingAPIError(504, msg, code="timeout") from e
            except httpx.RequestError as e:
                if attempt < self._retries:
                    await asyncio.sleep(1.0)
                    continue
                raise HandwritingAPIError(502, "Service unavailable") from e
            except (ValueError, TypeError) as e:
                # Response decoding/shape errors are not retriable here
                raise HandwritingAPIError(500, "Invalid response body") from e
        # Should never reach here; loop either returns or raises
        raise HandwritingAPIError(500, "Unexpected client error")  # pragma: no cover

    async def _attempt_read(
        self,
        url: str,
        headers: dict[str, str],
        files: dict[str, tuple[str, bytes, str]],
    ) -> PredictResult:
        resp = await self._client.post(url, headers=headers, files=files)
        if resp.status_code >= 400:
            raise _shape_api_error(resp)
        body_obj: object = resp.json()
        if not isinstance(body_obj, dict):
            raise HandwritingAPIError(500, "Invalid response body")
        return _parse_predict_result(body_obj)


def _parse_predict_result(d: dict[str, object]) -> PredictResult:
    def _num(x: object) -> float:
        return float(str(x))

    digit = int(str(d.get("digit", 0)))
    confidence = _num(d.get("confidence", 0.0))
    probs_val = d.get("probs", [])
    probs: tuple[float, ...] = (
        tuple(float(p) for p in probs_val) if isinstance(probs_val, list) else ()
    )
    model_id = str(d.get("model_id", ""))
    uncertain = bool(d.get("uncertain", False))
    latency_ms = int(str(d.get("latency_ms", 0)))
    return PredictResult(
        digit=digit,
        confidence=confidence,
        probs=probs,
        model_id=model_id,
        uncertain=uncertain,
        latency_ms=latency_ms,
    )


def _shape_api_error(resp: httpx.Response) -> HandwritingAPIError:
    status = int(resp.status_code)
    code: str | None = None
    message = f"HTTP {status}"
    request_id: str | None = resp.headers.get("X-Request-ID")
    try:
        obj: object = resp.json()
        if isinstance(obj, dict):
            raw_code = obj.get("code")
            code = str(raw_code) if isinstance(raw_code, str) else code
            raw_msg = obj.get("message")
            message = str(raw_msg) if isinstance(raw_msg, str) else message
            rid = obj.get("request_id")
            request_id = str(rid) if isinstance(rid, str) else request_id
    except (ValueError, TypeError):
        pass
    return HandwritingAPIError(status=status, message=message, code=code, request_id=request_id)
