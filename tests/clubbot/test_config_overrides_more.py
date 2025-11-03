from __future__ import annotations

from pathlib import Path

from src.clubbot.config import load_config


def test_parse_guilds_with_empty_and_invalid_tokens(monkeypatch) -> None:
    # Trailing delimiter produces an empty token; 'abc' is invalid numeric
    monkeypatch.setenv("DISCORD_GUILD_IDS", "123,456,abc,")
    monkeypatch.delenv("DISCORD_GUILD_ID", raising=False)
    cfg = load_config()
    assert cfg.DISCORD_GUILD_IDS == [123, 456]


def test_file_overrides_int_valid_and_invalid(tmp_path: Path, monkeypatch) -> None:
    toml_path = tmp_path / "clubbot.toml"
    toml_path.write_text(
        """
        RQ_TRANSCRIPT_RETRY_MAX = "7"
        RQ_TRANSCRIPT_JOB_TIMEOUT_SEC = "bad"
        """.strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("CLUBBOT_CONFIG", str(toml_path))
    # Ensure env defaults apply when override invalid
    monkeypatch.delenv("RQ_TRANSCRIPT_JOB_TIMEOUT_SEC", raising=False)
    cfg = load_config()
    # Valid override used
    assert cfg.RQ_TRANSCRIPT_RETRY_MAX == 7
    # Invalid override falls back to default (600)
    assert cfg.RQ_TRANSCRIPT_JOB_TIMEOUT_SEC == 600
