from __future__ import annotations

import asyncio

import httpx

from clubbot.services.modeltrainer.client import HTTPModelTrainerClient, ModelTrainerAPIError


def test_client_error_message_fallback_when_dict_has_empty_message() -> None:
    base = "https://example/api"

    def _handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover - sync handler
        if request.method.upper() == "POST" and str(request.url) == f"{base}/runs/train":
            return httpx.Response(418, json={"message": ""})
        return httpx.Response(404, json={"message": "not found"})

    transport = httpx.MockTransport(_handler)

    async def _run() -> None:
        client = HTTPModelTrainerClient(
            base_url=base, api_key="k", client=httpx.AsyncClient(transport=transport)
        )
        try:
            await client.train(
                user_id=1,
                model_family="gpt2",
                model_size="small",
                max_seq_len=32,
                num_epochs=1,
                batch_size=1,
                learning_rate=5e-4,
                corpus_path="/data/corpus",
                tokenizer_id="tok",
                request_id="r",
            )
            raise AssertionError("expected failure")
        except ModelTrainerAPIError as e:
            # Fallback should use HTTP status code in message
            assert e.status == 418
            assert "HTTP 418" in str(e)
        await client.aclose()

    asyncio.get_event_loop().run_until_complete(_run())
