from __future__ import annotations

import asyncio

import httpx

from clubbot.services.modeltrainer.client import HTTPModelTrainerClient, ModelTrainerAPIError


class _MockHandler:
    def __init__(self) -> None:
        self.routes: dict[tuple[str, str], callable] = {}

    def add(self, method: str, url: str, func):
        self.routes[(method.upper(), url)] = func

    def __call__(self, request: httpx.Request) -> httpx.Response:  # pragma: no cover - sync gateway
        key = (request.method.upper(), str(request.url))
        handler = self.routes.get(key)
        if handler is None:
            return httpx.Response(404, json={"message": "not found"})
        return handler(request)


def test_client_error_paths_and_status_conversion() -> None:
    mh = _MockHandler()
    base = "https://example/api"
    # Train: 400 with message in JSON
    mh.add("POST", f"{base}/runs/train", lambda req: httpx.Response(400, json={"message": "bad"}))
    # Status: 200 with heartbeat as string
    mh.add(
        "GET",
        f"{base}/runs/r1",
        lambda req: httpx.Response(
            200, json={"run_id": "r1", "status": "running", "last_heartbeat_ts": "12.5"}
        ),
    )

    transport = httpx.MockTransport(mh)

    async def _run() -> None:
        client = HTTPModelTrainerClient(
            base_url=base, api_key="k", client=httpx.AsyncClient(transport=transport)
        )
        try:
            await client.train(
                user_id=1,
                model_family="gpt2",
                model_size="small",
                max_seq_len=128,
                num_epochs=1,
                batch_size=2,
                learning_rate=5e-4,
                corpus_path="/data/corpus",
                tokenizer_id="tok1",
                request_id="req",
            )
            raise AssertionError("expected error")
        except ModelTrainerAPIError as e:
            assert e.status == 400
        st = await client.status(run_id="r1", request_id="req2")
        assert st.last_heartbeat_ts == 12.5
        await client.aclose()

    asyncio.get_event_loop().run_until_complete(_run())


def test_client_train_invalid_body_and_http_error_fallback() -> None:
    mh = _MockHandler()
    base = "https://example/api"
    mh.add("POST", f"{base}/runs/train", lambda req: httpx.Response(500, text="oops"))
    mh.add("GET", f"{base}/runs/x", lambda req: httpx.Response(200, json=[1, 2]))

    transport = httpx.MockTransport(mh)

    async def _run() -> None:
        client = HTTPModelTrainerClient(
            base_url=base, api_key="k", client=httpx.AsyncClient(transport=transport)
        )
        from clubbot.services.modeltrainer.client import ModelTrainerAPIError

        with pytest.raises(ModelTrainerAPIError) as e1:
            await client.train(
                user_id=1,
                model_family="gpt2",
                model_size="small",
                max_seq_len=128,
                num_epochs=1,
                batch_size=2,
                learning_rate=5e-4,
                corpus_path="/data/corpus",
                tokenizer_id="tok1",
                request_id="req",
            )
        assert "HTTP 500" in str(e1.value)

        with pytest.raises(ModelTrainerAPIError) as e2:
            await client.status(run_id="x", request_id="req2")
        assert "Invalid response body" in str(e2.value)
        await client.aclose()

    import pytest

    asyncio.get_event_loop().run_until_complete(_run())


def test_client_success_without_api_key_and_status_detail_message() -> None:
    mh = _MockHandler()
    base = "https://example/api"
    # Train success
    mh.add(
        "POST",
        f"{base}/runs/train",
        lambda req: httpx.Response(200, json={"run_id": "r2", "job_id": "j2"}),
    )
    # Status 404 with detail
    mh.add("GET", f"{base}/runs/r2", lambda req: httpx.Response(404, json={"detail": "oops"}))

    transport = httpx.MockTransport(mh)

    async def _run() -> None:
        client = HTTPModelTrainerClient(
            base_url=base,
            api_key=None,
            client=httpx.AsyncClient(transport=transport),
        )
        out = await client.train(
            user_id=2,
            model_family="gpt2",
            model_size="small",
            max_seq_len=128,
            num_epochs=1,
            batch_size=2,
            learning_rate=5e-4,
            corpus_path="/data/corpus",
            tokenizer_id="tok1",
            request_id="req3",
        )
        assert out.run_id == "r2" and out.job_id == "j2"
        from clubbot.services.modeltrainer.client import ModelTrainerAPIError

        try:
            await client.status(run_id=out.run_id, request_id="req4")
            raise AssertionError("expected status error")
        except ModelTrainerAPIError as e:
            assert "oops" in str(e)
        await client.aclose()

    asyncio.get_event_loop().run_until_complete(_run())
