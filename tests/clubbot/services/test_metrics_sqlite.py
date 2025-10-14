from src.clubbot.services.metrics import QRGenerationOptions, SQLiteMetricsService


def test_metrics_sqlite_basic_counts(tmp_path):
    db = tmp_path / "metrics.sqlite"
    ms = SQLiteMetricsService(str(db), redact_query=True)

    opts = QRGenerationOptions(
        ecc="M", box_size=10, border=2, fill_color="#000000", back_color="#FFFFFF"
    )

    # Log a success
    ms.log_qr_event(
        outcome="success",
        ts=None,
        user_id=1,
        guild_id=10,
        input_url="https://example.com/path?token=abc",
        normalized_url="https://example.com/path?token=abc",
        options=opts,
        public=True,
    )

    # Log a validation failure
    ms.log_qr_event(
        outcome="validation_fail",
        ts=None,
        user_id=2,
        guild_id=None,
        input_url="not a url",
        normalized_url=None,
        options=opts,
        public=False,
        error_type="invalid_url",
        error_message="bad",
    )

    totals = ms.summarize_totals(window_seconds=None)
    # One attempt failed, one succeeded
    assert totals["total_attempts"] == 2
    assert totals["total_success"] == 1
    assert totals["unique_users"] == 1
    assert totals["unique_guilds"] == 1  # guild 10 and DM bucket are distinct; only success counts
    assert totals["unique_links"] == 1

    top = ms.top_links(limit=5, window_seconds=None)
    # Redaction removes the query
    assert top[0]["url"] == "https://example.com/path"
    assert top[0]["count"] == 1

    br = ms.outcome_breakdown(window_seconds=None)
    assert br["success"] == 1
    assert br["validation_fail"] == 1
    assert br["rate_limited"] == 0
    assert br["internal_error"] == 0


def test_metrics_windows_and_outcomes(tmp_path):
    db = tmp_path / "metrics.sqlite"
    ms = SQLiteMetricsService(str(db), redact_query=True)

    opts = QRGenerationOptions(
        ecc="M", box_size=10, border=2, fill_color="#000000", back_color="#FFFFFF"
    )

    import time as _time

    now = int(_time.time())
    hour = 3600

    # Older than 24h window
    ms.log_qr_event(
        outcome="success",
        ts=now - (25 * hour),
        user_id=10,
        guild_id=100,
        input_url="https://a.com/old",
        normalized_url="https://a.com/old",
        options=opts,
        public=True,
    )

    # Inside 24h window
    ms.log_qr_event(
        outcome="success",
        ts=now - (2 * hour),
        user_id=11,
        guild_id=100,
        input_url="https://a.com/new?x=1",
        normalized_url="https://a.com/new?x=1",
        options=opts,
        public=True,
    )
    ms.log_qr_event(
        outcome="rate_limited",
        ts=now - (1 * hour),
        user_id=11,
        guild_id=100,
        input_url="https://a.com/new?x=1",
        normalized_url=None,
        options=opts,
        public=True,
        error_type="rate_limited",
    )
    ms.log_qr_event(
        outcome="internal_error",
        ts=now - (1 * hour),
        user_id=12,
        guild_id=None,
        input_url="https://b.com/boom",
        normalized_url=None,
        options=opts,
        public=False,
        error_type="exception",
        error_message="ValueError",
    )

    # 24h window should not include the old event
    totals_24h = ms.summarize_totals(window_seconds=24 * hour)
    assert totals_24h["total_attempts"] == 3
    assert totals_24h["total_success"] == 1
    assert totals_24h["unique_users"] == 1
    assert totals_24h["unique_guilds"] == 1  # success only counted

    br_24h = ms.outcome_breakdown(window_seconds=24 * hour)
    assert br_24h == {
        "success": 1,
        "validation_fail": 0,
        "rate_limited": 1,
        "internal_error": 1,
    }

    # Top links in 24h window
    top_24h = ms.top_links(limit=5, window_seconds=24 * hour)
    assert len(top_24h) == 1
    assert top_24h[0]["url"] == "https://a.com/new"
    assert top_24h[0]["count"] == 1


def test_metrics_redaction_toggle(tmp_path):
    db = tmp_path / "metrics.sqlite"
    ms = SQLiteMetricsService(str(db), redact_query=False)

    opts = QRGenerationOptions(
        ecc="M", box_size=10, border=2, fill_color="#000000", back_color="#FFFFFF"
    )

    ms.log_qr_event(
        outcome="success",
        ts=None,
        user_id=9,
        guild_id=99,
        input_url="https://c.com/path?token=secret",
        normalized_url="https://c.com/path?token=secret",
        options=opts,
        public=True,
    )

    top = ms.top_links(limit=1, window_seconds=None)
    assert top[0]["url"] == "https://c.com/path?token=secret"
