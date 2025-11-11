from __future__ import annotations

import asyncio
from types import SimpleNamespace

import discord

from clubbot.cogs.trainer import TrainerCog
from clubbot.config import load_config
from clubbot.services.modeltrainer.client import TrainResponse


class _Resp:
    def __init__(self) -> None:
        self._done = False

    def is_done(self) -> bool:
        return self._done

    async def defer(self, *, ephemeral: bool) -> None:
        self._done = True


class _Follow:
    def __init__(self) -> None:
        self.last_embed: discord.Embed | None = None

    async def send(self, embed: discord.Embed, ephemeral: bool = True) -> None:
        self.last_embed = embed


class _Interaction:
    def __init__(self) -> None:
        self.response = _Resp()
        self.followup = _Follow()
        self.user = SimpleNamespace(id=123)


class _ClientStub:
    class _Ctx:
        async def __aenter__(self) -> None:  # pragma: no cover - trivial
            return None

        async def __aexit__(self, exc_type, exc, tb) -> None:  # pragma: no cover - trivial
            return None

    def __init__(self) -> None:
        self._client = self._Ctx()

    async def aclose(self) -> None:
        return None

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
        return TrainResponse(run_id="r", job_id="j")


def test_trainer_cog_train_model_happy_path(monkeypatch) -> None:
    cfg = load_config()
    # Configure endpoint to enable cog
    object.__setattr__(cfg, "MODEL_TRAINER_API_URL", "https://example")
    cog = TrainerCog(bot=SimpleNamespace(), config=cfg)
    inter = _Interaction()

    async def _run() -> None:
        monkeypatch.setattr(cog, "_mk_client", lambda: _ClientStub())
        # Access the underlying command callback to invoke directly
        await TrainerCog.train_model.callback(
            cog,
            inter,
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
    assert isinstance(inter.followup.last_embed, discord.Embed)
