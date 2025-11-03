from __future__ import annotations

import importlib


def test_worker_entrypoint_is_importable() -> None:
    mod = importlib.import_module("clubbot.workers.transcript")
    fn = getattr(mod, "process_transcript_job", None)
    assert callable(fn)
