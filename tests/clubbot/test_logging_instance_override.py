from __future__ import annotations

from src.clubbot.logging import get_instance_id, setup_logging


def test_instance_id_explicit_override(monkeypatch) -> None:
    monkeypatch.setenv("BOT_INSTANCE_ID", "abc-123")
    setup_logging("INFO")
    assert get_instance_id() == "abc-123"
