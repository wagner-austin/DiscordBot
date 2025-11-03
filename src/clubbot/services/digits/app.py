from __future__ import annotations

from dataclasses import dataclass

from ...config import Config
from ..handai.client import HandwritingClient, HandwritingReader, PredictResult


@dataclass(frozen=True)
class DigitServiceConfig:
    base_url: str
    api_key: str | None
    timeout_seconds: int
    max_retries: int


class DigitService:
    def __init__(self, cfg: Config, client: HandwritingReader | None = None) -> None:
        if not cfg.HANDWRITING_API_URL:
            raise RuntimeError("HANDWRITING_API_URL is not configured")
        self._client: HandwritingReader = client or HandwritingClient(
            base_url=cfg.HANDWRITING_API_URL,
            api_key=cfg.HANDWRITING_API_KEY,
            timeout_seconds=int(cfg.HANDWRITING_API_TIMEOUT_SECONDS),
            max_retries=int(cfg.HANDWRITING_API_MAX_RETRIES),
        )
        self._max_image_mb: int = int(cfg.DIGITS_MAX_IMAGE_MB)

    @property
    def max_image_bytes(self) -> int:
        return self._max_image_mb * 1024 * 1024

    async def read_image(
        self, *, data: bytes, filename: str, content_type: str, request_id: str
    ) -> PredictResult:
        return await self._client.read_digit(
            data=data,
            filename=filename,
            content_type=content_type,
            request_id=request_id,
            center=True,
            visualize=False,
        )
