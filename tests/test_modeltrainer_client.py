from __future__ import annotations

import asyncio
from collections.abc import Callable

import httpx

from clubbot.services.modeltrainer.client import HTTPModelTrainerClient


class _MockHandler:
    def __init__(self) -> None:
        self.routes: dict[tuple[str, str], Callable[[httpx.Request], httpx.Response]] = {}

    def add(self, method: str, url: str, func: Callable[[httpx.Request], httpx.Response]) -> None:
        self.routes[(method.upper(), url)] = func

    def __call__(self, request: httpx.Request) -> httpx.Response:  # pragma: no cover - sync gateway
        key = (request.method.upper(), str(request.url))
        handler = self.routes.get(key)
        if handler is None:
            return httpx.Response(404, json={"message": "not found"})
        return handler(request)


def test_client_train_and_status_roundtrip() -> None:
    mh = _MockHandler()
    base = "https://example/api"
    # Train endpoint
    mh.add(
        "POST",
        f"{base}/runs/train",
        lambda req: httpx.Response(200, json={"run_id": "r123", "job_id": "j456"}),
    )
    # Status endpoint
    mh.add(
        "GET",
        f"{base}/runs/r123",
        lambda req: httpx.Response(
            200,
            json={"run_id": "r123", "status": "queued", "last_heartbeat_ts": None, "message": None},
        ),
    )

    transport = httpx.MockTransport(mh)

    async def _run() -> None:
        client = HTTPModelTrainerClient(
            base_url=base, api_key="k", client=httpx.AsyncClient(transport=transport)
        )
        out = await client.train(
            user_id=1,
            model_family="gpt2",
            model_size="small",
            max_seq_len=128,
            num_epochs=1,
            batch_size=2,
            learning_rate=5e-4,
            corpus_path="/data/corpus",
            tokenizer_id="tok1",
            request_id="req1",
        )
        assert out.run_id == "r123" and out.job_id == "j456"
        st = await client.status(run_id=out.run_id, request_id="req2")
        assert st.status == "queued" and st.run_id == "r123"
        await client.aclose()

    asyncio.get_event_loop().run_until_complete(_run())
