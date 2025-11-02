from __future__ import annotations

import os

import pytest
from src.clubbot.config import load_config, require_token


def _clear_env(keys: list[str]) -> None:
    for k in keys:
        os.environ.pop(k, None)


def test_retry_intervals_parsing_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RQ_TRANSCRIPT_RETRY_INTERVALS_SEC", "30,120")
    monkeypatch.setenv("DISCORD_TOKEN", "x")
    cfg = load_config()
    assert cfg.RQ_TRANSCRIPT_RETRY_INTERVALS_SEC == (30, 120)


def test_retry_intervals_parsing_invalid_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RQ_TRANSCRIPT_RETRY_INTERVALS_SEC", "abc,10")
    monkeypatch.setenv("DISCORD_TOKEN", "x")
    cfg = load_config()
    assert cfg.RQ_TRANSCRIPT_RETRY_INTERVALS_SEC == (60, 300)


@pytest.mark.parametrize(
    "val,expected",
    [
        ("1", True),
        ("true", True),
        ("yes", True),
        ("y", True),
        ("on", True),
        ("0", False),
        ("false", False),
        ("off", False),
    ],
)
def test_boolean_flags(monkeypatch: pytest.MonkeyPatch, val: str, expected: bool) -> None:
    # Test QR_PUBLIC_RESPONSES and TRANSCRIPT_PUBLIC_RESPONSES booleans
    monkeypatch.setenv("QR_PUBLIC_RESPONSES", val)
    monkeypatch.setenv("TRANSCRIPT_PUBLIC_RESPONSES", val)
    monkeypatch.setenv("DISCORD_TOKEN", "x")
    cfg = load_config()
    assert cfg.QR_PUBLIC_RESPONSES is expected
    assert cfg.TRANSCRIPT_PUBLIC_RESPONSES is expected


def test_guild_ids_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISCORD_GUILD_IDS", "1, 2  three  4")
    monkeypatch.setenv("DISCORD_TOKEN", "x")
    cfg = load_config()
    # Only numeric tokens are included
    assert cfg.DISCORD_GUILD_IDS == [1, 2, 4]


def test_openai_key_and_provider_lowercasing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("TRANSCRIPT_PROVIDER", "STT")
    monkeypatch.setenv("DISCORD_TOKEN", "x")
    cfg = load_config()
    assert cfg.OPENAI_API_KEY == "sk-test"
    assert cfg.TRANSCRIPT_PROVIDER == "stt"


def test_require_token_raises_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    # Ensure token is missing
    _clear_env(["DISCORD_TOKEN"])
    cfg = load_config()
    with pytest.raises(RuntimeError):
        require_token(cfg)
