from __future__ import annotations

import asyncio

import httpx
import pytest
from src.clubbot.services.handai.client import HandwritingAPIError, HandwritingClient


class _RespOK:
    def __init__(self, body: object) -> None:
        self.status_code = 200
        self._body = body

    def json(self) -> object:
        return self._body


class _RespJSONList:
    status_code = 200

    def json(self) -> object:
        return [1, 2, 3]


def _predict_body() -> dict[str, object]:
    return {
        "digit": 3,
        "confidence": 0.9,
        "probs": [0.1] * 10,
        "model_id": "m",
        "uncertain": False,
        "latency_ms": 12,
    }


@pytest.mark.asyncio
async def test_headers_include_api_key() -> None:
    seen = {}

    class _Client:
        async def post(self, url, headers, files):
            seen.update(headers)
            return _RespOK(_predict_body())

    hc = HandwritingClient(
        base_url="http://x",
        api_key="sekrit",
        timeout_seconds=1,
        max_retries=0,
        client=_Client(),
    )
    out = await hc.read_digit(
        data=b"x",
        filename="x.png",
        content_type="image/png",
        request_id="r",
    )
    assert out.digit == 3 and seen.get("X-Api-Key") == "sekrit"


@pytest.mark.asyncio
async def test_request_error_retries_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    class _Client:
        async def post(self, url, headers, files):
            calls["n"] += 1
            if calls["n"] == 1:
                raise httpx.RequestError("boom")
            return _RespOK(_predict_body())

    async def _fast_sleep(_t: float) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", _fast_sleep)
    hc = HandwritingClient(
        base_url="http://x",
        api_key=None,
        timeout_seconds=1,
        max_retries=1,
        client=_Client(),
    )
    out = await hc.read_digit(
        data=b"x",
        filename="x.png",
        content_type="image/png",
        request_id="r",
    )
    assert out.digit == 3 and calls["n"] == 2


@pytest.mark.asyncio
async def test_invalid_response_body_non_dict_raises() -> None:
    class _Client:
        async def post(self, url, headers, files):
            return _RespJSONList()

    hc = HandwritingClient(
        base_url="http://x",
        api_key=None,
        timeout_seconds=1,
        max_retries=0,
        client=_Client(),
    )
    with pytest.raises(HandwritingAPIError) as ei:
        await hc.read_digit(
            data=b"x",
            filename="x.png",
            content_type="image/png",
            request_id="r",
        )
    assert "Invalid response body" in str(ei.value)


def test_shape_api_error_json_list_defaults() -> None:
    from src.clubbot.services.handai.client import _shape_api_error

    resp = httpx.Response(503, json=[1, 2, 3], headers={"X-Request-ID": "rid2"})
    err = _shape_api_error(resp)
    assert err.status == 503 and err.request_id == "rid2" and "HTTP 503" in str(err)
