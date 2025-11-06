from __future__ import annotations

import pytest
import src.clubbot.config as cfg_mod
from src.clubbot.config import Config, load_config


def test_parse_guilds_single_invalid_warns(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level("WARNING")
    monkeypatch.setenv("DISCORD_GUILD_ID", "abc")
    single, ids = cfg_mod._parse_guilds()
    assert single == "abc" and ids == []
    assert any("Invalid DISCORD_GUILD_ID" in r.message for r in caplog.records)


def test_load_file_overrides_success(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    toml = tmp_path / "clubbot.toml"
    toml.write_text("QR_DEFAULT_BOX_SIZE=12\nTRANSCRIPT_PROVIDER='stt'\n", encoding="utf-8")
    monkeypatch.setenv("DISCORD_TOKEN", "x")
    monkeypatch.setenv("CLUBBOT_CONFIG", str(toml))
    cfg = load_config()
    assert cfg.QR_DEFAULT_BOX_SIZE == 12
    assert cfg.TRANSCRIPT_PROVIDER == "stt"


def test_load_file_overrides_oserror(
    monkeypatch: pytest.MonkeyPatch, tmp_path, caplog: pytest.LogCaptureFixture
) -> None:
    # Create a real file but force open() to raise OSError via monkeypatch
    toml = tmp_path / "clubbot.toml"
    toml.write_text("QR_DEFAULT_BORDER=3\n", encoding="utf-8")
    caplog.set_level("WARNING")

    monkeypatch.setenv("CLUBBOT_CONFIG", str(toml))
    import builtins as _builtins

    def _bad_open(path: str, mode: str, *a: object, **k: object) -> object:
        if path == str(toml) and "rb" in mode:
            raise OSError("cannot open")
        return _orig_open(path, mode, *a, **k)

    from collections.abc import Callable

    _orig_open: Callable[..., object] = _builtins.open
    monkeypatch.setattr(_builtins, "open", _bad_open, raising=True)
    # load_config will call _load_file_overrides which will warn and ignore
    monkeypatch.setenv("DISCORD_TOKEN", "x")
    cfg = load_config()
    assert isinstance(cfg, Config)
    assert any("Failed to read config file" in r.message for r in caplog.records)


def test_boolean_and_float_parsing_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    # Provide invalid floats to ensure defaults used
    monkeypatch.setenv("TRANSCRIPT_STT_RTF", "bad")
    monkeypatch.setenv("TRANSCRIPT_DL_MIB_PER_SEC", "bad")
    monkeypatch.setenv("DISCORD_TOKEN", "x")
    cfg = load_config()
    assert cfg.TRANSCRIPT_STT_RTF == 0.5
    assert cfg.TRANSCRIPT_DL_MIB_PER_SEC == 4.0


def test_admin_ids_and_youtube_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QR_STATS_ADMIN_USER_IDS", "1, x, 2, 03")
    monkeypatch.setenv("YOUTUBE_API_KEY", "")
    monkeypatch.setenv("DISCORD_TOKEN", "x")
    cfg = load_config()
    assert cfg.QR_STATS_ADMIN_USER_IDS == [1, 2, 3]
    assert cfg.YOUTUBE_API_KEY is None


def test_float_helper_empty_uses_default(monkeypatch: pytest.MonkeyPatch) -> None:
    # Ensure missing/empty env returns default
    monkeypatch.delenv("X_FAKE_FLOAT", raising=False)
    assert cfg_mod._f("X_FAKE_FLOAT", 1.23) == 1.23


def test_redis_url_none_when_blank(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISCORD_TOKEN", "x")
    monkeypatch.setenv("REDIS_URL", " ")
    cfg = load_config()
    assert cfg.REDIS_URL is None


def test_int_helper_valid_and_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    # Valid integer path
    monkeypatch.setenv("DISCORD_TOKEN", "x")
    monkeypatch.setenv("QRCODE_RATE_LIMIT", "5")
    cfg = load_config()
    assert cfg.QRCODE_RATE_LIMIT == 5
    # Invalid (fallback to default)
    monkeypatch.setenv("QRCODE_RATE_LIMIT", "bad")
    cfg2 = load_config()
    assert cfg2.QRCODE_RATE_LIMIT == 1


def test_load_file_overrides_non_dict_ignored(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    # Force tomllib.load to return a non-dict object to exercise the branch
    toml = tmp_path / "clubbot.toml"
    toml.write_text("[section]\nkey=1\n", encoding="utf-8")
    monkeypatch.setenv("CLUBBOT_CONFIG", str(toml))
    monkeypatch.setenv("DISCORD_TOKEN", "x")

    import tomllib as _tomllib

    def _fake_load(_f: object) -> object:
        return [1, 2, 3]

    monkeypatch.setattr(_tomllib, "load", _fake_load, raising=True)
    cfg = load_config()
    # Should fall back to defaults (i.e., a real Config still created)
    assert isinstance(cfg, Config)
