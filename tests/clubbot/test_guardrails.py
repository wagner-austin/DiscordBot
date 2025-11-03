from __future__ import annotations

import os
from pathlib import Path

SRC = Path("src")


def test_no_cast_or_any_in_src() -> None:
    patterns = ["cast(", " from typing import Any", "typing.Any"]
    for p in SRC.rglob("*.py"):
        text = p.read_text(encoding="utf-8", errors="ignore")
        for pat in patterns:
            assert pat not in text, f"Disallowed pattern '{pat}' found in {p}"


def test_no_blind_except_outside_cogs() -> None:
    # Allow cogs to catch Exception to standardize user messaging
    allowed = {
        "src/clubbot/cogs/",
        "src/clubbot/orchestrator.py",
        "src/clubbot/services/transcript/app.py",
        "src/clubbot/services/transcript/provider.py",
        "src/clubbot/services/transcript/stt_provider.py",
        "src/clubbot/services/jobs/runner.py",
        "src/clubbot/services/jobs/queue.py",
        "scripts/",
        "src/clubbot/utils/",
    }
    for p in SRC.rglob("*.py"):
        norm = str(p).replace(os.sep, "/")
        if any(a in norm for a in allowed):
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        assert "except Exception" not in text, f"Blind except in {p} is not allowed"


def test_no_type_ignore_comments_in_src() -> None:
    for p in SRC.rglob("*.py"):
        text = p.read_text(encoding="utf-8", errors="ignore")
        # Enforce only actual mypy ignore comments, not string mentions
        assert "# type: ignore" not in text, f"Found '# type: ignore' in {p}"


def test_no_type_ignore_comments_in_tests() -> None:
    tests = Path("tests")
    for p in tests.rglob("*.py"):
        text = p.read_text(encoding="utf-8", errors="ignore")
        # Skip this guard file to avoid false positives from string literals
        if p.name == "test_guardrails.py":
            continue
        assert "# type: ignore" not in text, f"Found '# type: ignore' in {p}"
