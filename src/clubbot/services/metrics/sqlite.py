from __future__ import annotations

import logging
import os
import sqlite3
import time
from pathlib import Path

from .service import MetricsService
from .types import LinkCount, OutcomeBreakdown, QRGenerationOptions, Totals


def _ensure_dir(path: str) -> None:
    p = Path(path)
    if not p.is_dir():
        p.mkdir(parents=True, exist_ok=True)


def _redact_query(url: str) -> str:
    qpos = url.find("?")
    return url if qpos == -1 else url[:qpos]


class SQLiteMetricsService(MetricsService):
    def __init__(self, sqlite_path: str, redact_query: bool = True) -> None:
        self.sqlite_path = sqlite_path
        self.redact_query = redact_query
        db_dir = os.path.dirname(sqlite_path) or "."
        _ensure_dir(db_dir)
        self._conn = sqlite3.connect(sqlite_path, check_same_thread=False)
        self._logger = logging.getLogger(__name__)
        self._logger.debug("Metrics init: path=%s redact_query=%s", sqlite_path, redact_query)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS qr_events (
                id INTEGER PRIMARY KEY,
                ts INTEGER NOT NULL,
                outcome TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                guild_id INTEGER,
                input_url TEXT NOT NULL,
                normalized_url TEXT,
                ecc TEXT NOT NULL,
                box_size INTEGER NOT NULL,
                border INTEGER NOT NULL,
                fill_color TEXT NOT NULL,
                back_color TEXT NOT NULL,
                public INTEGER NOT NULL,
                error_type TEXT,
                error_message TEXT
            )
            """
        )
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_qr_ts ON qr_events(ts)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_qr_outcome_ts ON qr_events(outcome, ts)")
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_qr_url_ts ON qr_events(normalized_url, ts)"
        )
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_qr_user_ts ON qr_events(user_id, ts)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_qr_guild_ts ON qr_events(guild_id, ts)")
        self._conn.commit()

    def close(self) -> None:
        import contextlib

        with contextlib.suppress(Exception):
            self._conn.close()

    def log_qr_event(
        self,
        *,
        outcome: str,
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
        now = int(time.time()) if ts is None else ts
        norm = normalized_url
        if norm and self.redact_query:
            norm = _redact_query(norm)
        self._logger.debug(
            "Log QR event outcome=%s user=%s guild=%s url=%s norm=%s",
            outcome,
            user_id,
            guild_id,
            input_url,
            norm,
        )
        self._conn.execute(
            """
            INSERT INTO qr_events(ts, outcome, user_id, guild_id, input_url, normalized_url,
                                  ecc, box_size, border, fill_color, back_color, public,
                                  error_type, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now,
                outcome,
                int(user_id),
                int(guild_id) if guild_id is not None else None,
                input_url,
                norm,
                options.ecc,
                options.box_size,
                options.border,
                options.fill_color,
                options.back_color,
                1 if public else 0,
                error_type,
                error_message,
            ),
        )
        self._conn.commit()

    def _window_clause(
        self, window_seconds: int | None
    ) -> tuple[str, tuple[int]] | tuple[str, tuple[()]]:
        if window_seconds is None:
            return "", ()
        cutoff = int(time.time()) - int(window_seconds)
        return " WHERE ts >= ?", (cutoff,)

    def summarize_totals(self, window_seconds: int | None) -> Totals:
        where, args = self._window_clause(window_seconds)
        cur = self._conn.cursor()
        total_attempts = cur.execute(f"SELECT COUNT(*) FROM qr_events{where}", args).fetchone()[0]
        total_success = cur.execute(
            "SELECT COUNT(*) FROM qr_events WHERE outcome='success'"
            + (where.replace(" WHERE", " AND") if where else ""),
            args,
        ).fetchone()[0]
        unique_users = cur.execute(
            "SELECT COUNT(DISTINCT user_id) FROM qr_events WHERE outcome='success'"
            + (where.replace(" WHERE", " AND") if where else ""),
            args,
        ).fetchone()[0]
        unique_guilds = cur.execute(
            "SELECT COUNT(DISTINCT COALESCE(guild_id,-1)) FROM qr_events WHERE outcome='success'"
            + (where.replace(" WHERE", " AND") if where else ""),
            args,
        ).fetchone()[0]
        unique_links = cur.execute(
            "SELECT COUNT(DISTINCT normalized_url) FROM qr_events WHERE outcome='success'"
            + " AND normalized_url IS NOT NULL"
            + (where.replace(" WHERE", " AND") if where else ""),
            args,
        ).fetchone()[0]
        return {
            "total_attempts": int(total_attempts),
            "total_success": int(total_success),
            "unique_users": int(unique_users),
            "unique_guilds": int(unique_guilds),
            "unique_links": int(unique_links),
        }

    def top_links(self, limit: int, window_seconds: int | None) -> list[LinkCount]:
        where, args = self._window_clause(window_seconds)
        cur = self._conn.cursor()
        rows = cur.execute(
            (
                "SELECT normalized_url, COUNT(*) AS c FROM qr_events "
                "WHERE outcome='success' AND normalized_url IS NOT NULL"
                + (where.replace(" WHERE", " AND") if where else "")
                + " GROUP BY normalized_url ORDER BY c DESC LIMIT ?"
            ),
            (*args, int(limit)),
        ).fetchall()
        return [{"url": str(r[0]), "count": int(r[1])} for r in rows]

    def outcome_breakdown(self, window_seconds: int | None) -> OutcomeBreakdown:
        where, args = self._window_clause(window_seconds)
        cur = self._conn.cursor()
        rows = cur.execute(
            f"SELECT outcome, COUNT(*) FROM qr_events{where} GROUP BY outcome",
            args,
        ).fetchall()
        out: OutcomeBreakdown = {
            "success": 0,
            "validation_fail": 0,
            "rate_limited": 0,
            "internal_error": 0,
        }
        for name, count in rows:
            c = int(count)
            if name == "success":
                out["success"] = c
            elif name == "validation_fail":
                out["validation_fail"] = c
            elif name == "rate_limited":
                out["rate_limited"] = c
            elif name == "internal_error":
                out["internal_error"] = c
        return out
