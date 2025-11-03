from __future__ import annotations

from pathlib import Path

from src.clubbot.services.metrics.sqlite import SQLiteMetricsService
from src.clubbot.services.metrics.types import QRGenerationOptions


def test_sqlite_metrics_creates_directory_and_close(tmp_path: Path) -> None:
    db_dir = tmp_path / "nested" / "dir"
    db_path = db_dir / "metrics.sqlite"
    m = SQLiteMetricsService(sqlite_path=str(db_path), redact_query=True)
    # Path should be created by constructor
    assert db_dir.is_dir()

    # Log an event with a URL that includes a query to exercise redaction path
    m.log_qr_event(
        outcome="success",
        ts=None,
        user_id=42,
        guild_id=None,
        input_url="https://example.com/hello?x=1",
        normalized_url="https://example.com/hello?x=1",
        options=QRGenerationOptions(
            ecc="M",
            box_size=10,
            border=1,
            fill_color="#000000",
            back_color="#FFFFFF",
        ),
        public=True,
    )

    # Totals should be consistent
    totals = m.summarize_totals(None)
    assert totals["total_attempts"] >= 1
    # Close covers the contextlib.suppress branch
    m.close()
