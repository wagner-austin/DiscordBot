import pytest
from src.clubbot.utils.errors import UserInputError
from src.clubbot.utils.validators import (
    validate_border,
    validate_box_size,
    validate_color,
    validate_ecc,
    validate_url,
)


def test_validate_url_ok():
    assert validate_url("https://example.com") == "https://example.com"
    # Adds https:// for bare hostnames
    assert validate_url("example.com") == "https://example.com"
    assert validate_url("www.example.org/path?q=1") == "https://www.example.org/path?q=1"


def test_validate_url_bad():
    with pytest.raises(UserInputError):
        validate_url("")
    with pytest.raises(UserInputError):
        validate_url("not a url with spaces")


def test_validate_color_hex():
    assert validate_color("#FF00FF", "#000") == "#FF00FF"


def test_validate_color_named():
    assert validate_color("red", "#000000") == "red"


def test_validate_color_invalid():
    with pytest.raises(UserInputError):
        validate_color("not-a-color", "#000000")


def test_validate_ecc_ok():
    assert validate_ecc("H", "M") == "H"


def test_validate_ecc_invalid():
    with pytest.raises(UserInputError):
        validate_ecc("X", "M")


def test_validate_box_size_bounds():
    assert validate_box_size(5, 10) == 5
    assert validate_box_size(20, 10) == 20
    with pytest.raises(UserInputError):
        validate_box_size(4, 10)
    with pytest.raises(UserInputError):
        validate_box_size(21, 10)


def test_validate_border_bounds():
    assert validate_border(1, 4) == 1
    assert validate_border(10, 4) == 10
    with pytest.raises(UserInputError):
        validate_border(0, 4)
    with pytest.raises(UserInputError):
        validate_border(11, 4)
