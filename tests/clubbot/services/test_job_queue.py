from __future__ import annotations

from src.clubbot.services.jobs.queue import TranscriptJob, _parse_job_payload


def test_parse_job_payload_valid() -> None:
    s = '{"request_id":"abcd1234","url":"https://x","user_id":123}'
    job = _parse_job_payload(s)
    assert isinstance(job, TranscriptJob)
    assert job.request_id == "abcd1234"
    assert job.user_id == 123


def test_parse_job_payload_invalid() -> None:
    # Missing fields
    assert _parse_job_payload("{}") is None
    # Wrong types
    assert _parse_job_payload('{"request_id": 1, "url": [], "user_id": "x"}') is None
    # Not JSON
    assert _parse_job_payload("not-json") is None
