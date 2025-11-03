from __future__ import annotations

from src.clubbot.services.metrics.service import NullMetricsService


def test_null_metrics_all_methods_return_sane_defaults() -> None:
    m = NullMetricsService()
    # log_qr_event should not raise
    m.log_qr_event(
        outcome="success",
        ts=None,
        user_id=1,
        guild_id=None,
        input_url="https://x",
        normalized_url="https://x?q=1",
        options={
            "ecc": "M",
            "box_size": 10,
            "border": 1,
            "fill_color": "#000",
            "back_color": "#fff",
        },
        public=True,
    )
    totals = m.summarize_totals(None)
    assert totals["total_attempts"] == 0 and totals["unique_links"] == 0
    top = m.top_links(5, None)
    assert top == []
    ob = m.outcome_breakdown(None)
    assert ob == {
        "success": 0,
        "validation_fail": 0,
        "rate_limited": 0,
        "internal_error": 0,
    }
