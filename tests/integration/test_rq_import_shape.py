from __future__ import annotations


def test_rq_exposes_retry_top_level() -> None:
    # Enforce the project's chosen RQ import shape
    from rq import Retry

    assert callable(Retry)
