import pytest
from src.clubbot.utils.errors import UserInputError
from src.clubbot.utils.youtube import extract_video_id, validate_youtube_url


def test_extract_video_id_variants() -> None:
    vid = "dQw4w9WgXcQ"
    assert extract_video_id(f"https://www.youtube.com/watch?v={vid}") == vid
    assert extract_video_id(f"https://youtu.be/{vid}") == vid
    assert extract_video_id(f"https://www.youtube.com/shorts/{vid}") == vid
    assert extract_video_id(f"www.youtube.com/watch?v={vid}") == vid


def test_validate_not_youtube() -> None:
    with pytest.raises(UserInputError):
        validate_youtube_url("https://example.com/watch?v=abc")


def test_invalid_id() -> None:
    with pytest.raises(UserInputError):
        extract_video_id("https://youtu.be/too_short")
