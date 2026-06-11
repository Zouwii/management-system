"""DingTalk API call monitor — SQL-backed with in-memory cache.

- Every API call is persisted to api_call_logs table.
- Memory cache keeps recent 200 calls for instant response.
- Aggregated stats queried from DB (today).
"""

import datetime as dt
import threading
import time
from typing import List, Optional


class ApiCallMonitor:
    """Singleton monitor. DB-persisted + in-memory recent buffer."""

    _instance: Optional["ApiCallMonitor"] = None
    _lock = threading.Lock()

    def __init__(self):
        self._lock = threading.Lock()
        self._started_at = time.time()
        self._recent: List[dict] = []  # ring buffer, max 200
        self._batch: List[dict] = []   # pending batch for DB insert
        self._batch_lock = threading.Lock()

    @classmethod
    def get(cls) -> "ApiCallMonitor":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @staticmethod
    def _today_key() -> str:
        return dt.datetime.utcnow().strftime("%Y-%m-%d")

    def record(self, endpoint: str, status: int, latency_ms: int, error: str = "",
               source: str = ""):
        """Record a single API call — memory buffer + DB persist."""
        now = time.time()
        entry = {
            "ts": now,
            "endpoint": endpoint,
            "source": source,
            "status": status,
            "latency_ms": latency_ms,
            "error": error,
        }

        # Memory ring buffer
        with self._lock:
            self._recent.append(entry)
            if len(self._recent) > 200:
                self._recent = self._recent[-200:]

        # DB batch (non-blocking, flushed on snapshot or at threshold)
        with self._batch_lock:
            self._batch.append(entry)
            if len(self._batch) >= 50:
                self._flush_batch()

    def _flush_batch(self):
        """Write pending entries to DB."""
        if not self._batch:
            return
        to_write = list(self._batch)
        self._batch.clear()
        try:
            from base.db.engine import SessionLocal
            from base.db.orm import ApiCallLog
            session = SessionLocal()
            try:
                now = dt.datetime.utcnow()
                for e in to_write:
                    session.add(ApiCallLog(
                        endpoint=e["endpoint"],
                        source=e.get("source", ""),
                        status=e["status"],
                        latency_ms=e["latency_ms"],
                        error_msg=e.get("error", ""),
                        created_at=now,
                    ))
                session.commit()
            finally:
                session.close()
        except Exception:
            pass

    def snapshot(self, day: str = "") -> dict:
        """Return stats: DB aggregation for the given day (default today UTC).
        Queries DB on every call."""

        # Flush pending batch first
        self._flush_batch()

        today = day or self._today_key()

        # Query DB for today's stats
        db_stats = self._query_stats_for_day(today)
        total_calls = db_stats.get("total", 0)
        total_errors = db_stats.get("errors", 0)
        endpoints = db_stats.get("endpoints", {})
        recent = db_stats.get("recent", [])

        # Top 5
        top = sorted(endpoints.items(), key=lambda x: -x[1]["calls"])[:5]

        uptime_sec = int(time.time() - self._started_at)
        uptime_str = f"{uptime_sec // 3600}h {(uptime_sec % 3600) // 60}m {uptime_sec % 60}s"

        error_rate = round(total_errors / max(total_calls, 1) * 100, 1)

        return {
            "ok": True,
            "uptime": uptime_str,
            "day": today,
            "total_calls": total_calls,
            "total_errors": total_errors,
            "error_rate_pct": error_rate,
            "top_endpoints": {path: endpoints[path] for path, _ in top},
            "all_endpoints": endpoints,
            "recent": recent,
            "disabled": _is_sync_disabled(),
        }

    @staticmethod
    def _query_stats_for_day(day: str) -> dict:
        """Query API call stats from MySQL for a specific day (YYYY-MM-DD, UTC)."""
        try:
            from base.db.engine import SessionLocal
            from sqlalchemy import text
            session = SessionLocal()
            try:
                row = session.execute(text(
                    "SELECT COUNT(*) as total, "
                    "SUM(CASE WHEN status >= 400 THEN 1 ELSE 0 END) as errors "
                    "FROM api_call_logs WHERE DATE(created_at) = :today"
                ), {"today": day}).fetchone()
                total = int(row.total) if row and row.total else 0
                errors = int(row.errors) if row and row.errors else 0

                endpoint_rows = session.execute(text(
                    "SELECT endpoint, COUNT(*) as cnt, "
                    "SUM(CASE WHEN status >= 400 THEN 1 ELSE 0 END) as err_cnt, "
                    "ROUND(AVG(latency_ms), 1) as avg_ms "
                    "FROM api_call_logs WHERE DATE(created_at) = :day "
                    "GROUP BY endpoint ORDER BY cnt DESC"
                ), {"day": day}).fetchall()

                endpoints = {}
                for r in endpoint_rows:
                    endpoints[r.endpoint] = {
                        "calls": r.cnt,
                        "errors": r.err_cnt,
                        "avg_latency_ms": float(r.avg_ms or 0),
                    }

                recent_rows = session.execute(text(
                    "SELECT endpoint, source, status, latency_ms, error_msg, created_at "
                    "FROM api_call_logs WHERE DATE(created_at) = :day "
                    "ORDER BY id DESC LIMIT 50"
                ), {"day": day}).fetchall()

                recent = []
                for r in recent_rows:
                    recent.append({
                        "ts": r.created_at.timestamp() if r.created_at else 0,
                        "endpoint": r.endpoint,
                        "source": r.source or "",
                        "status": r.status,
                        "latency_ms": r.latency_ms,
                        "error": r.error_msg or "",
                    })

                return {
                    "total": total,
                    "errors": errors,
                    "endpoints": endpoints,
                    "recent": recent,
                }
            finally:
                session.close()
        except Exception:
            return {"total": 0, "errors": 0, "endpoints": {}, "recent": []}


# Global instance
monitor = ApiCallMonitor.get()


def record_api_call(endpoint: str, status: int, latency_ms: int, error: str = "",
                    source: str = ""):
    """Convenience function to record an API call."""
    monitor.record(endpoint, status, latency_ms, error, source)


def _is_sync_disabled() -> bool:
    try:
        from pathlib import Path
        flag = Path(__file__).resolve().parent.parent / "runtime" / "sync_disabled"
        return flag.exists()
    except Exception:
        return False
