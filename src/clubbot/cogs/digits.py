from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Final

import discord
from discord import app_commands
from discord.ext import commands

from ..config import Config
from ..logging import set_request_id
from ..services.digits.app import DigitService
from ..services.handai.client import HandwritingAPIError, PredictResult
from ..utils.errors import UserInputError
from ..utils.rate_limiter import RateLimiter
from .base import BaseCog

_PNG: Final[str] = "image/png"
_JPEG: Final[str] = "image/jpeg"
_JPG: Final[str] = "image/jpg"
_ALLOWED: Final[tuple[str, ...]] = (_PNG, _JPEG, _JPG)


class DigitsCog(BaseCog):
    def __init__(self, bot: commands.Bot, config: Config, service: DigitService) -> None:
        super().__init__()
        self.bot = bot
        self.config = config
        self.service = service
        self.rate_limiter = RateLimiter(config.DIGITS_RATE_LIMIT, config.DIGITS_RATE_WINDOW_SECONDS)

    @app_commands.command(name="read", description="Recognize a handwritten digit from an image")
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.describe(image="PNG or JPEG image of a single digit")
    async def read(self, interaction: discord.Interaction, image: discord.Attachment) -> None:
        # Ack first to avoid 3s timeout; silence stale/duplicates
        if not await self._ack_interaction(interaction):
            return

        request_id = self.new_request_id()
        set_request_id(request_id)
        log = self.request_logger(request_id)
        user_id = self._extract_int_attr(interaction.user, "id")
        if user_id is None:
            await self.handle_user_error(interaction, log, "Could not determine your user id")
            return

        # Rate limit
        allowed, wait_seconds = self.rate_limiter.allow(user_id, "read")
        if not allowed:
            await interaction.followup.send(
                f"Please wait {int(wait_seconds)} seconds before requesting another read",
                ephemeral=not self.config.DIGITS_PUBLIC_RESPONSES,
            )
            log.info("Rate limited user=%s", user_id)
            return

        try:
            self._validate_attachment(image)
            data = await image.read()
            result = await self.service.read_image(
                data=data,
                filename=image.filename or "image",
                content_type=image.content_type or "",
                request_id=request_id,
            )
        except UserInputError as e:
            await self.handle_user_error(interaction, log, str(e))
            return
        except HandwritingAPIError as e:
            msg = _user_message_from_api_error(e)
            if 400 <= e.status < 500:
                await self.handle_user_error(interaction, log, msg)
            else:
                await self.handle_exception(interaction, log, e)
            return
        except Exception as exc:
            await self.handle_exception(interaction, log, exc)
            return

        content = _format_result(result)
        await interaction.followup.send(
            content=content, ephemeral=not self.config.DIGITS_PUBLIC_RESPONSES
        )
        log.info("Digit read sent successfully")

    async def _ack_interaction(self, interaction: discord.Interaction) -> bool:
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=not self.config.DIGITS_PUBLIC_RESPONSES)
            return True
        except discord.NotFound as e:
            logging.getLogger(__name__).debug("Interaction expired before defer; skipping: %s", e)
            return False
        except discord.HTTPException as e:
            # 40060: Interaction already acknowledged
            if getattr(e, "code", None) == 40060:
                logging.getLogger(__name__).debug("Interaction already acknowledged; continuing")
                return True
            logging.getLogger(__name__).exception("Failed to defer interaction: %s", e)
            from contextlib import suppress

            with suppress(Exception):
                await interaction.followup.send(
                    "An error occurred. Please try again.", ephemeral=True
                )
            return False
        except Exception as e:  # pragma: no cover - unexpected
            logging.getLogger(__name__).exception("Failed to defer interaction: %s", e)
            from contextlib import suppress

            with suppress(Exception):
                await interaction.followup.send(
                    "An error occurred. Please try again.", ephemeral=True
                )
            return False

    @staticmethod
    def _extract_int_attr(obj: object | None, name: str) -> int | None:
        if obj is None:
            return None
        value = getattr(obj, name, None)
        return value if isinstance(value, int) else None

    def _validate_attachment(self, att: discord.Attachment) -> None:
        ctype = (att.content_type or "").lower()
        if ctype not in _ALLOWED:
            raise UserInputError("Unsupported file type; please upload a PNG or JPEG image")
        max_bytes = self.service.max_image_bytes
        size = int(getattr(att, "size", 0) or 0)
        if size > 0 and size > max_bytes:
            mb = max_bytes // (1024 * 1024)
            raise UserInputError(f"Image is too large (max {mb} MB)")


def _top_k_indices(probs: Iterable[float], k: int = 3) -> list[int]:
    items = list(enumerate(float(p) for p in probs))
    items.sort(key=lambda kv: kv[1], reverse=True)
    return [items[i][0] for i in range(min(k, len(items)))]


def _format_result(res: PredictResult) -> str:
    top3 = _top_k_indices(res.probs, 3)
    parts = [f"Digit: {res.digit} ({res.confidence * 100:.1f}% confidence)."]
    top_parts = [f"{i}={res.probs[i]:.3f}" for i in top3]
    parts.append(f"Top-3: {', '.join(top_parts)}.")
    parts.append(f"Model: {res.model_id}.")
    if res.uncertain:
        parts.append("Low confidence; try larger digits or darker ink.")
    return " ".join(parts)


def _user_message_from_api_error(e: HandwritingAPIError) -> str:
    if e.status == 401:
        return "Service is not authorized. Please contact an admin."
    if e.status == 413 or (e.code == "too_large"):
        return "Image is too large."
    if e.status == 415 or (e.code == "unsupported_media_type"):
        return "Unsupported file type; please upload a PNG or JPEG image."
    if e.status == 400 and (e.code in {"invalid_image", "bad_dimensions", "preprocessing_failed"}):
        return "Could not process image. Please try another image."
    if e.status == 504 or e.code == "timeout":
        return "Service timed out; please try again."
    return f"Request failed (status={e.status}). Please try again."
