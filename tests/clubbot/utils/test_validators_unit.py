from __future__ import annotations

import pytest
from src.clubbot.utils.errors import UserInputError
from src.clubbot.utils.validators import (
    validate_border,
    validate_box_size,
    validate_color,
    validate_ecc,
    validate_url,
)


def test_url_too_long_raises() -> None:
    long_host = "a" * 2001
    with pytest.raises(UserInputError) as ei:
        validate_url(long_host)
    assert "too long" in str(ei.value)


def test_url_invalid_format_via_monkeypatch(monkeypatch: pytest.MonkeyPatch) -> None:
    # Force urllib.parse.urlsplit to raise to exercise error path
    import urllib.parse as _url

    def _boom(url: str) -> object:  # minimal stub signature
        raise ValueError("bad parse")

    monkeypatch.setattr(_url, "urlsplit", _boom)
    with pytest.raises(UserInputError) as ei:
        validate_url("example.com")
    assert "Invalid URL format" in str(ei.value)


def test_url_scheme_rejected_if_not_http_https() -> None:
    with pytest.raises(UserInputError) as ei:
        validate_url("ftp://example.com")
    assert "scheme" in str(ei.value).lower()


def test_ipv6_and_port_are_accepted() -> None:
    out = validate_url("https://[2001:db8::1]:8443/path?q=1")
    assert out.startswith("https://[2001:db8::1]:8443/")


def test_port_stripping_for_validation_does_not_break_url() -> None:
    out = validate_url("https://example.com:8080/hello")
    assert out.endswith("/hello")


def test_missing_host_is_rejected() -> None:
    with pytest.raises(UserInputError) as ei:
        validate_url("https://")
    assert "host is required" in str(ei.value)


def test_malformed_host_gives_friendly_message() -> None:
    with pytest.raises(UserInputError) as ei:
        validate_url("https://-bad..host/")
    assert "Please check the URL" in str(ei.value)


def test_validate_color_defaults_and_variants() -> None:
    # None → default
    assert validate_color(None, "#ffffff") == "#ffffff"
    # Whitespace-only is considered invalid, not default
    with pytest.raises(UserInputError):
        validate_color("  ", "#abc")
    # Hex preserved
    assert validate_color("#ff0000", "#000") == "#ff0000"
    # Named color
    assert validate_color("red", "#000") == "red"
    # Bad color raises
    with pytest.raises(UserInputError):
        validate_color("not-a-color", "#000")


def test_validate_ecc_default_and_errors() -> None:
    assert validate_ecc(None, "M") == "M"
    assert validate_ecc("l", "M") == "L"
    with pytest.raises(UserInputError):
        validate_ecc("Z", "M")


def test_validate_box_size_default_and_bounds() -> None:
    assert validate_box_size(None, 10) == 10
    assert validate_box_size(5, 10) == 5
    assert validate_box_size(20, 10) == 20
    with pytest.raises(UserInputError):
        validate_box_size(4, 10)
    with pytest.raises(UserInputError):
        validate_box_size(21, 10)


def test_validate_border_default_and_bounds() -> None:
    assert validate_border(None, 2) == 2
    assert validate_border(1, 2) == 1
    assert validate_border(10, 2) == 10
    with pytest.raises(UserInputError):
        validate_border(0, 2)
    with pytest.raises(UserInputError):
        validate_border(11, 2)
