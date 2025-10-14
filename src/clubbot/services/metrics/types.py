from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypedDict


@dataclass(frozen=True)
class QRGenerationOptions:
    ecc: str
    box_size: int
    border: int
    fill_color: str
    back_color: str


OutcomeLiteral = Literal[
    "success",
    "validation_fail",
    "rate_limited",
    "internal_error",
]

OUTCOME_SUCCESS: OutcomeLiteral = "success"
OUTCOME_VALIDATION_FAIL: OutcomeLiteral = "validation_fail"
OUTCOME_RATE_LIMITED: OutcomeLiteral = "rate_limited"
OUTCOME_INTERNAL_ERROR: OutcomeLiteral = "internal_error"


class Totals(TypedDict):
    total_attempts: int
    total_success: int
    unique_users: int
    unique_guilds: int
    unique_links: int


class LinkCount(TypedDict):
    url: str
    count: int


class OutcomeBreakdown(TypedDict):
    success: int
    validation_fail: int
    rate_limited: int
    internal_error: int


def parse_window(spec: str | None) -> int | None:
    if not spec or spec == "all":
        return None
    s = spec.strip().lower()
    if s.endswith("h"):
        return int(float(s[:-1]) * 3600)
    if s.endswith("d"):
        return int(float(s[:-1]) * 86400)
    if s.isdigit():
        return int(s)
    return None
