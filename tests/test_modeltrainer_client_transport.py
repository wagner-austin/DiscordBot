from __future__ import annotations

import asyncio

import httpx

from clubbot.services.modeltrainer.client import HTTPModelTrainerClient, ModelTrainerAPIError


def test_transport_errors_raise_502() -> None:
    class _Handler:
        def __call__(self, request: httpx.Request) -> httpx.Response:
            raise AssertionError  # pragma: no cover - never called

    # Use transporter that raises during request
    def _raise_req(request: httpx.Request) -> httpx.Response:  # pragma: no cover - sync stub
        raise httpx.ConnectError("conn", request=request)

    transport = httpx.MockTransport(_raise_req)

    async def _run() -> None:
        client = HTTPModelTrainerClient(
            base_url="https://example/api",
            api_key="k",
            client=httpx.AsyncClient(transport=transport),
        )
        try:
            await client.train(
                user_id=1,
                model_family="gpt2",
                model_size="small",
                max_seq_len=16,
                num_epochs=1,
                batch_size=1,
                learning_rate=5e-4,
                corpus_path="/data",
                tokenizer_id="tok",
                request_id="r",
            )
            raise AssertionError("expected error")
        except ModelTrainerAPIError as e:
            assert e.status == 502
        try:
            await client.status(run_id="x", request_id="r2")
            raise AssertionError("expected error")
        except ModelTrainerAPIError as e:
            assert e.status == 502
        await client.aclose()

    asyncio.get_event_loop().run_until_complete(_run())
