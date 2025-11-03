from __future__ import annotations

from src.clubbot.services.metrics.types import parse_window


def test_parse_window_all_and_none() -> None:
    assert parse_window(None) is None
    assert parse_window("all") is None


def test_parse_window_hours_and_days() -> None:
    assert parse_window("1h") == 3600
    assert parse_window("0.5h") == int(0.5 * 3600)
    assert parse_window("2d") == 2 * 86400


def test_parse_window_plain_seconds_and_invalid() -> None:
    assert parse_window("600") == 600
    assert parse_window("nonsense") is None
