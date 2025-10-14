from __future__ import annotations

import logging
from typing import Protocol

from .types import (
    LinkCount,
    OutcomeBreakdown,
    OutcomeLiteral,
    QRGenerationOptions,
    Totals,
)


class MetricsService(Protocol):
    def log_qr_event(
        self,
        *,
        outcome: OutcomeLiteral,
        ts: int | None,
        user_id: int,
        guild_id: int | None,
        input_url: str,
        normalized_url: str | None,
        options: QRGenerationOptions,
        public: bool,
        error_type: str | None = None,
        error_message: str | None = None,
    ) -> None: ...

    def summarize_totals(self, window_seconds: int | None) -> Totals: ...

    def top_links(self, limit: int, window_seconds: int | None) -> list[LinkCount]: ...

    def outcome_breakdown(self, window_seconds: int | None) -> OutcomeBreakdown: ...


class NullMetricsService:
    def __init__(self) -> None:
        self._logger = logging.getLogger(__name__)

    def log_qr_event(
        self,
        *,
        outcome: OutcomeLiteral,
        ts: int | None,
        user_id: int,
        guild_id: int | None,
        input_url: str,
        normalized_url: str | None,
        options: QRGenerationOptions,
        public: bool,
        error_type: str | None = None,
        error_message: str | None = None,
    ) -> None:
        self._logger.debug("(Null) metrics: %s", outcome)

    def summarize_totals(self, window_seconds: int | None) -> Totals:
        return {
            "total_attempts": 0,
            "total_success": 0,
            "unique_users": 0,
            "unique_guilds": 0,
            "unique_links": 0,
        }

    def top_links(self, limit: int, window_seconds: int | None) -> list[LinkCount]:
        return []

    def outcome_breakdown(self, window_seconds: int | None) -> OutcomeBreakdown:
        return {
            "success": 0,
            "validation_fail": 0,
            "rate_limited": 0,
            "internal_error": 0,
        }
