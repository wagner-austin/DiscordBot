from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from ..cogs.base import BaseCog
from ..config import Config
from ..logging import set_request_id
from ..services.jobs.trainer_events import DEFAULT_TRAINER_EVENTS_CHANNEL
from ..services.jobs.trainer_notifier import TrainerEventSubscriber
from ..services.modeltrainer.client import HTTPModelTrainerClient, ModelTrainerAPIError
from ..utils.errors import UserInputError
from ..utils.rate_limiter import RateLimiter


class TrainerCog(BaseCog):
    def __init__(self, bot: commands.Bot, config: Config) -> None:
        super().__init__()
        self.bot = bot
        self.config = config
        self.rate_limiter = RateLimiter(1, 10)
        self._subscriber = None
        redis_url = (getattr(self.config, "REDIS_URL", None) or "").strip()
        if redis_url:
            try:
                sub = TrainerEventSubscriber(
                    self.bot, redis_url=redis_url, events_channel=DEFAULT_TRAINER_EVENTS_CHANNEL
                )
                sub.start()
                self._subscriber = sub
                logging.getLogger(__name__).info(
                    "Trainer events subscriber started (channel=%s)", DEFAULT_TRAINER_EVENTS_CHANNEL
                )
            except (RuntimeError, ValueError, ImportError, OSError, TypeError) as e:
                logging.getLogger(__name__).warning(
                    "Failed to start trainer events subscriber: %s", e
                )

    def _mk_client(self) -> HTTPModelTrainerClient:
        base = (self.config.MODEL_TRAINER_API_URL or "").strip()
        if not base:
            raise UserInputError("Model Trainer API is not configured")
        return HTTPModelTrainerClient(
            base_url=base,
            api_key=(self.config.MODEL_TRAINER_API_KEY or None),
            timeout_seconds=int(self.config.MODEL_TRAINER_API_TIMEOUT_SECONDS),
        )

    @app_commands.command(name="train_model", description="Start a model training run")
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.describe(
        model_family="Model family (e.g., gpt2)",
        model_size="Model size label (e.g., small)",
        max_seq_len="Max sequence length",
        num_epochs="Number of epochs",
        batch_size="Batch size",
        learning_rate="Learning rate",
        corpus_path="Path to corpus in API container (e.g., /data/corpus)",
        tokenizer_id="Tokenizer artifact ID",
    )
    async def train_model(
        self,
        interaction: discord.Interaction,
        model_family: str,
        model_size: str,
        max_seq_len: int,
        num_epochs: int,
        batch_size: int,
        learning_rate: float,
        corpus_path: str,
        tokenizer_id: str,
    ) -> None:
        if not await self._ack_interaction(interaction):
            return
        request_id = self.new_request_id()
        set_request_id(request_id)
        log = self.request_logger(request_id)
        user_id = self._extract_int_attr(interaction.user, "id")
        if user_id is None:
            await self.handle_user_error(interaction, log, "Could not determine your user id")
            return
        allowed, wait_seconds = self.rate_limiter.allow(user_id, "train_model")
        if not allowed:
            await interaction.followup.send(
                f"Please wait {int(wait_seconds)} seconds before starting another training run",
                ephemeral=True,
            )
            log.info("Rate limited user=%s", user_id)
            return
        try:
            client = self._mk_client()
            async with client._client as _:
                res = await client.train(
                    user_id=user_id,
                    model_family=model_family,
                    model_size=model_size,
                    max_seq_len=max_seq_len,
                    num_epochs=num_epochs,
                    batch_size=batch_size,
                    learning_rate=learning_rate,
                    corpus_path=corpus_path,
                    tokenizer_id=tokenizer_id,
                    request_id=request_id,
                )
        except UserInputError as e:
            await self.handle_user_error(interaction, log, str(e))
            return
        except ModelTrainerAPIError as e:
            await self.handle_user_error(interaction, log, f"API error: {e}")
            return
        except Exception as exc:
            await self.handle_exception(interaction, log, exc)
            return
        embed = discord.Embed(
            title="Training Job Queued",
            description=(
                "Your training job has been queued successfully!\n"
                "You'll receive DM updates with progress and results."
            ),
            color=0x5865F2,
        )
        embed.add_field(name="Run ID", value=f"`{res.run_id}`", inline=True)
        embed.add_field(name="Job ID", value=f"`{res.job_id}`", inline=True)
        embed.set_footer(text=f"Request ID: {request_id}")
        await interaction.followup.send(embed=embed, ephemeral=True)
        log.info("Queued training req=%s run=%s job=%s", request_id, res.run_id, res.job_id)

    async def _ack_interaction(self, interaction: discord.Interaction) -> bool:
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
            return True
        except discord.NotFound as e:
            logging.getLogger(__name__).debug(
                "Interaction expired before defer; skipping response: %s", e
            )
            return False
        except discord.HTTPException as e:
            if getattr(e, "code", None) == 40060:
                logging.getLogger(__name__).debug(
                    "Interaction already acknowledged; continuing without defer"
                )
                return True
            logging.getLogger(__name__).exception("Failed to defer interaction: %s", e)
            return False
        except Exception as e:  # pragma: no cover - unexpected
            logging.getLogger(__name__).exception("Failed to defer interaction: %s", e)
            return False

    @staticmethod
    def _extract_int_attr(obj: object | None, name: str) -> int | None:
        if obj is None:
            return None
        value = getattr(obj, name, None)
        return value if isinstance(value, int) else None
