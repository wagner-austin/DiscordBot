from __future__ import annotations

from pathlib import Path

from src.clubbot.services.metrics.sqlite import SQLiteMetricsService
from src.clubbot.services.metrics.types import QRGenerationOptions


def test_outcome_breakdown_internal_only(tmp_path: Path) -> None:
    db = tmp_path / "metrics.sqlite"
    ms = SQLiteMetricsService(str(db), redact_query=True)
    opts = QRGenerationOptions(ecc="M", box_size=10, border=1, fill_color="#000", back_color="#FFF")

    ms.log_qr_event(
        outcome="internal_error",
        ts=None,
        user_id=1,
        guild_id=None,
        input_url="https://err",
        normalized_url=None,
        options=opts,
        public=False,
        error_type="e",
        error_message="m",
    )

    br = ms.outcome_breakdown(window_seconds=None)
    assert br == {"success": 0, "validation_fail": 0, "rate_limited": 0, "internal_error": 1}
