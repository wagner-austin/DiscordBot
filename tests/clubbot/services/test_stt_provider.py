import os
import tempfile

import pytest
from src.clubbot.services.transcript.stt_provider import STTTranscriptProvider
from src.clubbot.services.transcript.types import TranscriptOptions, TranscriptSegment
from src.clubbot.utils.errors import UserInputError


def _touch_file(bytes_size: int) -> str:
    fd, path = tempfile.mkstemp(prefix="stt_test_", suffix=".bin")
    with os.fdopen(fd, "wb") as f:
        f.write(b"0" * bytes_size)
    return path


class NoopProvider(STTTranscriptProvider):
    def __post_init__(self) -> None:
        # Skip OpenAI client init for unit tests
        self._logger = __import__("logging").getLogger(__name__)
        self._client = None  # not used because we stub _transcribe


def test_stt_provider_rejects_long_video(monkeypatch: pytest.MonkeyPatch) -> None:
    p = NoopProvider(api_key="test", max_video_seconds=10, max_file_mb=25)
    monkeypatch.setattr(p, "_probe", lambda url: {"duration": 60})
    with pytest.raises(UserInputError):
        p.fetch("abc123xyz00", TranscriptOptions(preferred_langs=["en"]))


def test_stt_provider_rejects_large_file(monkeypatch: pytest.MonkeyPatch) -> None:
    p = NoopProvider(api_key="test", max_video_seconds=9999, max_file_mb=1)
    monkeypatch.setattr(p, "_probe", lambda url: {"duration": 60})
    big = _touch_file(2 * 1024 * 1024)
    try:
        monkeypatch.setattr(p, "_download_audio", lambda url: big)
        with pytest.raises(UserInputError):
            p.fetch("abc123xyz00", TranscriptOptions(preferred_langs=["en"]))
    finally:
        with __import__("contextlib").suppress(Exception):
            os.remove(big)


def test_stt_provider_success(monkeypatch: pytest.MonkeyPatch) -> None:
    p = NoopProvider(api_key="test", max_video_seconds=9999, max_file_mb=25)
    monkeypatch.setattr(p, "_probe", lambda url: {"duration": 60})
    small = _touch_file(1024)
    try:
        monkeypatch.setattr(p, "_download_audio", lambda url: small)
        segs = [
            TranscriptSegment(text="hello", start=0.0, duration=1.0),
            TranscriptSegment(text="world", start=1.0, duration=1.0),
        ]
        monkeypatch.setattr(p, "_transcribe", lambda path: segs)
        # The provider returns dataclass TranscriptSegment, but we can compare len and fields
        out = p.fetch("abc123xyz00", TranscriptOptions(preferred_langs=["en"]))
        assert len(out) == 2
        assert out[0].text == "hello" and out[1].text == "world"
    finally:
        with __import__("contextlib").suppress(Exception):
            os.remove(small)
