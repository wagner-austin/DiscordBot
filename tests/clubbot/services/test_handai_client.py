from __future__ import annotations

import httpx
import pytest
from src.clubbot.services.handai.client import HandwritingAPIError, HandwritingClient


@pytest.mark.asyncio
async def test_client_success() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        body = {
            "digit": 7,
            "confidence": 0.987,
            "probs": [1.0 if i == 7 else 0.0 for i in range(10)],
            "model_id": "mnist_resnet18_v1",
            "visual_png_b64": None,
            "uncertain": False,
            "latency_ms": 12,
        }
        return httpx.Response(200, json=body)

    transport = httpx.MockTransport(handler)
    client = HandwritingClient(
        base_url="http://example",
        api_key=None,
        client=httpx.AsyncClient(transport=transport, timeout=5.0),
    )
    res = await client.read_digit(
        data=b"png",
        filename="x.png",
        content_type="image/png",
        request_id="req1",
    )
    assert res.digit == 7 and res.model_id == "mnist_resnet18_v1"
    await client.aclose()


@pytest.mark.asyncio
async def test_client_unsupported_media_maps_error() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        body = {
            "code": "unsupported_media_type",
            "message": "Only PNG and JPEG are supported",
            "request_id": "r",
        }
        return httpx.Response(415, json=body)

    transport = httpx.MockTransport(handler)
    client = HandwritingClient(
        base_url="http://example",
        api_key=None,
        client=httpx.AsyncClient(transport=transport, timeout=5.0),
    )
    with pytest.raises(HandwritingAPIError) as ei:
        await client.read_digit(
            data=b"x",
            filename="x.txt",
            content_type="text/plain",
            request_id="req2",
        )
    e = ei.value
    assert e.status == 415 and (e.code == "unsupported_media_type" or e.code is None)
    await client.aclose()


@pytest.mark.asyncio
async def test_client_retry_on_timeout_then_success() -> None:
    calls = {"n": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.TimeoutException("timeout")
        return httpx.Response(
            200,
            json={
                "digit": 0,
                "confidence": 0.5,
                "probs": [0.1] * 10,
                "model_id": "m",
                "visual_png_b64": None,
                "uncertain": False,
                "latency_ms": 1,
            },
        )

    transport = httpx.MockTransport(handler)
    client = HandwritingClient(
        base_url="http://example",
        api_key=None,
        timeout_seconds=1,
        max_retries=1,
        client=httpx.AsyncClient(transport=transport, timeout=1.0),
    )
    res = await client.read_digit(
        data=b"x", filename="x.png", content_type="image/png", request_id="r"
    )
    assert res.digit == 0 and calls["n"] == 2
    await client.aclose()
