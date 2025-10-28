from src.clubbot.config import Config
from src.clubbot.services.transcript.app import TranscriptService
from src.clubbot.services.transcript.types import TranscriptOptions, TranscriptSegment


class FakeProvider:
    def fetch(self, video_id: str, opts: TranscriptOptions) -> list[TranscriptSegment]:
        assert video_id == "dQw4w9WgXcQ"
        return [
            TranscriptSegment(text="00:00:01.000 Hello", start=1.0, duration=1.0),
            TranscriptSegment(text="world 00:00:02.000", start=2.0, duration=1.0),
        ]


def make_cfg() -> Config:
    return Config(
        DISCORD_TOKEN="test",
        DISCORD_GUILD_ID=None,
        DISCORD_GUILD_IDS=[],
        LOG_LEVEL="INFO",
        QRCODE_RATE_LIMIT=1,
        QRCODE_RATE_WINDOW_SECONDS=1,
        QR_DEFAULT_ERROR_CORRECTION="M",
        QR_DEFAULT_BOX_SIZE=10,
        QR_DEFAULT_BORDER=2,
        QR_DEFAULT_FILL_COLOR="#000000",
        QR_DEFAULT_BACK_COLOR="#FFFFFF",
        QR_PUBLIC_RESPONSES=True,
        TRANSCRIPT_PUBLIC_RESPONSES=False,
    )


def test_transcript_service_cleans_and_canonicalizes_url():
    cfg = make_cfg()
    svc = TranscriptService(cfg)
    # Inject fake provider for offline test
    svc._set_provider_for_tests(FakeProvider())

    res = svc.fetch_cleaned("https://youtu.be/dQw4w9WgXcQ")
    assert res.video_id == "dQw4w9WgXcQ"
    assert res.url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert "00:00:" not in res.text
    assert "Hello" in res.text and "world" in res.text
