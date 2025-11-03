from __future__ import annotations

from types import SimpleNamespace

import pytest
from src.clubbot.services.digits.app import DigitService


def _cfg(url: str | None, mb: int = 2) -> SimpleNamespace:
    return SimpleNamespace(
        HANDWRITING_API_URL=url,
        HANDWRITING_API_KEY=None,
        HANDWRITING_API_TIMEOUT_SECONDS=5,
        HANDWRITING_API_MAX_RETRIES=1,
        DIGITS_MAX_IMAGE_MB=mb,
    )


def test_digit_service_requires_base_url() -> None:
    with pytest.raises(RuntimeError):
        DigitService(_cfg(None))


@pytest.mark.asyncio
async def test_digit_service_max_bytes_and_forward(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Client:
        async def read_digit(self, **kwargs):
            # Echo a minimal PredictResult-like structure for assertions
            return SimpleNamespace(
                digit=7,
                confidence=0.5,
                probs=(),
                model_id="m",
                uncertain=False,
                latency_ms=1,
            )

    svc = DigitService(_cfg("http://localhost", mb=3), client=_Client())
    # Property uses MB → bytes conversion
    assert svc.max_image_bytes == 3 * 1024 * 1024
    out = await svc.read_image(
        data=b"img", filename="x.png", content_type="image/png", request_id="r"
    )
    assert out.digit == 7
