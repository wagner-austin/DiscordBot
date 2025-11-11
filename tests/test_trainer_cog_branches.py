from __future__ import annotations

import asyncio
from types import SimpleNamespace

import discord
import pytest

from clubbot.cogs.trainer import TrainerCog
from clubbot.config import load_config
from clubbot.services.modeltrainer.client import ModelTrainerAPIError, TrainResponse


class _Resp:
    def __init__(self, *, raise_kind: str | None = None) -> None:
        self._done = False
        self._raise = raise_kind

    def is_done(self) -> bool:
        return self._done

    async def defer(self, *, ephemeral: bool) -> None:
        if self._raise == "notfound":
            raise discord.NotFound(
                SimpleNamespace(status=404, reason="Not Found"), message="gone"
            )
        if self._raise == "http_other":
            raise discord.HTTPException(
                SimpleNamespace(status=400, reason="Bad Request"), message="boom"
            )
        if self._raise == "http_40060":

            class _HTTPExc(discord.HTTPException):
                def __init__(self) -> None:
                    super().__init__(SimpleNamespace(status=400, reason="Bad Request"), "boom")
                    # Match the specific code path in _ack_interaction
                    self.code = 40060

            raise _HTTPExc()
        self._done = True


class _Follow:
    def __init__(self) -> None:
        self.last_content: str | None = None
        self.last_embed: discord.Embed | None = None

    async def send(
        self,
        content: str | None = None,
        embed: discord.Embed | None = None,
        ephemeral: bool = True,
    ) -> None:
        self.last_content = content
        self.last_embed = embed


class _Interaction:
    def __init__(self, *, resp: _Resp) -> None:
        self.response = resp
        self.followup = _Follow()
        self.user = SimpleNamespace(id=123)


def _cog_with_endpoint(monkeypatch) -> TrainerCog:
    cfg = load_config()
    object.__setattr__(cfg, "MODEL_TRAINER_API_URL", "https://example")
    return TrainerCog(bot=SimpleNamespace(), config=cfg)


def test_mk_client_not_configured() -> None:
    cfg = load_config()
    # Ensure empty
    object.__setattr__(cfg, "MODEL_TRAINER_API_URL", "")
    cog = TrainerCog(bot=SimpleNamespace(), config=cfg)
    from clubbot.utils.errors import UserInputError

    with pytest.raises(UserInputError):
        _ = cog._mk_client()


def test_subscriber_wiring_success(monkeypatch) -> None:
    cfg = load_config()
    object.__setattr__(cfg, "MODEL_TRAINER_API_URL", "https://example")
    object.__setattr__(cfg, "REDIS_URL", "redis://example")
    started: dict[str, int] = {"n": 0}

    class _Sub:
        def __init__(self, *a, **k) -> None:
            pass

        def start(self) -> None:
            started["n"] += 1

    monkeypatch.setattr("clubbot.cogs.trainer.TrainerEventSubscriber", _Sub)
    _ = TrainerCog(bot=SimpleNamespace(), config=cfg)
    assert started["n"] == 1


def test_subscriber_wiring_failure(monkeypatch) -> None:
    cfg = load_config()
    object.__setattr__(cfg, "MODEL_TRAINER_API_URL", "https://example")
    object.__setattr__(cfg, "REDIS_URL", "redis://example")

    class _Sub:
        def __init__(self, *a, **k) -> None:
            raise ImportError("x")

    monkeypatch.setattr("clubbot.cogs.trainer.TrainerEventSubscriber", _Sub)
    # Should not raise
    _ = TrainerCog(bot=SimpleNamespace(), config=cfg)


def test_ack_branches(monkeypatch) -> None:
    cog = _cog_with_endpoint(monkeypatch)
    # already acknowledged by response -> True
    i = _Interaction(resp=_Resp())
    i.response._done = True  # mark done
    assert asyncio.get_event_loop().run_until_complete(cog._ack_interaction(i)) is True
    # NotFound -> False
    inter2 = _Interaction(resp=_Resp(raise_kind="notfound"))
    assert asyncio.get_event_loop().run_until_complete(cog._ack_interaction(inter2)) is False
    # HTTPException other -> False
    inter3 = _Interaction(resp=_Resp(raise_kind="http_other"))
    assert asyncio.get_event_loop().run_until_complete(cog._ack_interaction(inter3)) is False


def test_ack_http_40060(monkeypatch) -> None:
    cog = _cog_with_endpoint(monkeypatch)
    inter = _Interaction(resp=_Resp(raise_kind="http_40060"))
    assert asyncio.get_event_loop().run_until_complete(cog._ack_interaction(inter)) is True


def test_train_model_early_return_on_ack(monkeypatch) -> None:
    cog = _cog_with_endpoint(monkeypatch)

    async def _no_ack(*a, **k) -> bool:
        return False

    monkeypatch.setattr(cog, "_ack_interaction", _no_ack)

    async def _run() -> None:
        await TrainerCog.train_model.callback(
            cog,
            _Interaction(resp=_Resp()),
            model_family="gpt2",
            model_size="small",
            max_seq_len=16,
            num_epochs=1,
            batch_size=1,
            learning_rate=5e-4,
            corpus_path="/data/corpus",
            tokenizer_id="tok",
        )

    asyncio.get_event_loop().run_until_complete(_run())


def test_train_model_user_id_none(monkeypatch) -> None:
    cog = _cog_with_endpoint(monkeypatch)
    seen: dict[str, str] = {}

    async def _handle_user_error(inter, log, msg):
        seen["msg"] = msg

    monkeypatch.setattr(cog, "_extract_int_attr", lambda *_: None)
    monkeypatch.setattr(cog, "handle_user_error", _handle_user_error, raising=False)

    async def _run() -> None:
        await TrainerCog.train_model.callback(
            cog,
            _Interaction(resp=_Resp()),
            model_family="gpt2",
            model_size="small",
            max_seq_len=16,
            num_epochs=1,
            batch_size=1,
            learning_rate=5e-4,
            corpus_path="/data/corpus",
            tokenizer_id="tok",
        )

    asyncio.get_event_loop().run_until_complete(_run())
    assert "user id" in seen.get("msg", "")


def test_train_model_mk_client_user_error(monkeypatch) -> None:
    cog = _cog_with_endpoint(monkeypatch)
    from clubbot.utils.errors import UserInputError

    async def _handle_user_error(inter, log, msg):
        inter.followup.last_content = msg

    monkeypatch.setattr(cog, "_mk_client", lambda: (_ for _ in ()).throw(UserInputError("cfg")))
    monkeypatch.setattr(cog, "handle_user_error", _handle_user_error, raising=False)
    i = _Interaction(resp=_Resp())

    async def _run() -> None:
        await TrainerCog.train_model.callback(
            cog,
            i,
            model_family="gpt2",
            model_size="small",
            max_seq_len=16,
            num_epochs=1,
            batch_size=1,
            learning_rate=5e-4,
            corpus_path="/data/corpus",
            tokenizer_id="tok",
        )

    asyncio.get_event_loop().run_until_complete(_run())
    assert i.followup.last_content and "cfg" in i.followup.last_content


def test_extract_int_attr_none() -> None:
    cfg = load_config()
    cog = TrainerCog(bot=SimpleNamespace(), config=cfg)
    assert cog._extract_int_attr(None, "id") is None


def test_mk_client_configured_returns_client() -> None:
    cfg = load_config()
    object.__setattr__(cfg, "MODEL_TRAINER_API_URL", "https://example")
    cog = TrainerCog(bot=SimpleNamespace(), config=cfg)
    client = cog._mk_client()
    from clubbot.services.modeltrainer.client import HTTPModelTrainerClient

    assert isinstance(client, HTTPModelTrainerClient)


def test_train_model_rate_limited(monkeypatch) -> None:
    cog = _cog_with_endpoint(monkeypatch)
    monkeypatch.setattr(cog.rate_limiter, "allow", lambda *_: (False, 3))
    i = _Interaction(resp=_Resp())

    async def _run() -> None:
        await TrainerCog.train_model.callback(
            cog,
            i,
            model_family="gpt2",
            model_size="small",
            max_seq_len=16,
            num_epochs=1,
            batch_size=1,
            learning_rate=5e-4,
            corpus_path="/data/corpus",
            tokenizer_id="tok",
        )

    asyncio.get_event_loop().run_until_complete(_run())
    assert i.followup.last_content and "Please wait" in i.followup.last_content


def test_train_model_api_error_and_exception(monkeypatch) -> None:
    cog = _cog_with_endpoint(monkeypatch)

    # API error path
    class _Client:
        class _Ctx:
            async def __aenter__(self) -> None:
                return None

            async def __aexit__(self, exc_type, exc, tb) -> None:
                return None

        def __init__(self) -> None:
            self._client = self._Ctx()

        async def train(self, **_: object) -> TrainResponse:
            raise ModelTrainerAPIError(400, "bad")

    monkeypatch.setattr(cog, "_mk_client", lambda: _Client())
    i1 = _Interaction(resp=_Resp())
    monkeypatch.setattr(cog.rate_limiter, "allow", lambda *_: (True, 0))

    async def _run1() -> None:
        await TrainerCog.train_model.callback(
            cog,
            i1,
            model_family="gpt2",
            model_size="small",
            max_seq_len=16,
            num_epochs=1,
            batch_size=1,
            learning_rate=5e-4,
            corpus_path="/data/corpus",
            tokenizer_id="tok",
        )

    asyncio.get_event_loop().run_until_complete(_run1())
    assert i1.followup.last_content and "API error" in i1.followup.last_content

    # Generic exception path
    class _Client2(_Client):
        async def train(self, **_: object) -> TrainResponse:
            raise RuntimeError("boom")

    monkeypatch.setattr(cog, "_mk_client", lambda: _Client2())
    i2 = _Interaction(resp=_Resp())

    async def _run2() -> None:
        await TrainerCog.train_model.callback(
            cog,
            i2,
            model_family="gpt2",
            model_size="small",
            max_seq_len=16,
            num_epochs=1,
            batch_size=1,
            learning_rate=5e-4,
            corpus_path="/data/corpus",
            tokenizer_id="tok",
        )

    asyncio.get_event_loop().run_until_complete(_run2())
    assert i2.followup.last_content and "An error occurred" in i2.followup.last_content
