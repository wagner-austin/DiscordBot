from src.clubbot.services.transcript.cleaner import clean_segments, strip_timestamps
from src.clubbot.services.transcript.types import TranscriptSegment


def test_strip_timestamps_from_free_text() -> None:
    raw = (
        'Elissa Newport: “Developmental plasticity and language learning..." # '
        "https://www.youtube.com/watch?v=2M7SO3gyA-4 00:00:00.000 No text 00:00:04.520 "
        "okay thank you so much for that lovely introduction 00:00:10.559"
    )
    cleaned = strip_timestamps(raw)
    assert "00:00:00.000" not in cleaned
    assert "00:00:10.559" not in cleaned
    assert "No text" not in cleaned


def test_clean_segments_joins_and_cleans() -> None:
    segs = [
        TranscriptSegment(text="00:00:01.000 hello", start=1.0, duration=2.0),
        TranscriptSegment(text="world 00:00:02.000", start=3.0, duration=2.0),
    ]
    out = clean_segments(segs)
    assert "00:00:" not in out
    assert "hello" in out and "world" in out
