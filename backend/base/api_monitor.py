"""DingTalk API call monitor — SQL-backed.

- Every API call is persisted to api_call_logs table.
- Batch flush: accumulates 50 entries before writing to DB.
- Aggregated stats queried from DB (today).
- 所有日期判断使用北京时间 (UTC+8)。
"""

import datetime as dt
import threading
import time
from datetime import timedelta, timezone
from typing import Optional

BJ_TZ = timezone(timedelta(hours=8))


def _bj_now() -> dt.datetime:
    """返回北京时间 now"""
    return dt.datetime.now(BJ_TZ)


class ApiCallMonitor:
    """Singleton monitor. DB-persisted with batch flush."""

    _instance: Optional["ApiCallMonitor"] = None
    _lock = threading.Lock()

    def __init__(self):
        self._started_at = time.time()
        self._batch: list = []   # pending batch for DB insert
        self._batch_lock = threading.Lock()
        self._last_record_at: float = time.time()

    @classmethod
    def get(cls) -> "ApiCallMonitor":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def record(self, endpoint: str, status: int, latency_ms: int, error: str = "",
               source: str = ""):
        """Record a single API call — accumulate for batch flush (50条或60秒)."""
        with self._batch_lock:
            now = time.time()
            # 超过 60 秒无新记录 → 先 flush 旧 batch，避免长期滞留内存
            if self._batch and now - self._last_record_at > 60:
                self._flush_batch()
            self._last_record_at = now
            self._batch.append({
                "endpoint": endpoint,
                "source": source,
                "status": status,
                "latency_ms": latency_ms,
                "error": error,
            })
            if len(self._batch) >= 50:
                self._flush_batch()

    def _flush_batch(self):
        """Write pending entries to DB, then check/enforce daily API limit."""
        if not self._batch:
            return
        to_write = list(self._batch)
        self._batch.clear()
        try:
            from base.db.engine import SessionLocal
            from base.db.orm import ApiCallLog
            session = SessionLocal()
            try:
                now = _bj_now()
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

        # 写入后检查用量，超限自动降级同步
        self._ensure_state()

    def _daily_limit(self) -> int:
        """当日硬限额（100%）：每月1号 15000，其他 5000"""
        return 15000 if _bj_now().day == 1 else 5000

    def _soft_limit(self) -> int:
        """当日软限额（80%）：硬限额 × 0.8"""
        return int(self._daily_limit() * 0.8)

    def _today_count(self) -> int:
        """查询当天 api_call_logs 记录数"""
        try:
            from base.db.engine import SessionLocal
            from sqlalchemy import text
            session = SessionLocal()
            try:
                today_str = _bj_now().strftime("%Y-%m-%d")
                row = session.execute(text(
                    "SELECT COUNT(*) FROM api_call_logs WHERE DATE(created_at) = :today"
                ), {"today": today_str}).fetchone()
                return int(row[0]) if row else 0
            finally:
                session.close()
        except Exception:
            return 0

    def _ensure_state(self) -> str:
        """根据当前用量调整 knowledge_sync_enabled 状态（三态：true/partial/false）。
        仅写入数据库；不记录 API 调用本身。"""
        cnt = self._today_count()
        soft = self._soft_limit()
        hard = self._daily_limit()

        if cnt >= hard:
            desired = "false"
        elif cnt >= soft:
            desired = "partial"
        else:
            desired = "true"

        try:
            from base.db.engine import SessionLocal
            from base.db.orm import Config
            session = SessionLocal()
            try:
                row = session.query(Config).filter(Config.type_ == "knowledge_sync_enabled").first()
                current = str(row.value).strip().lower() if row else "true"
                if current == desired:
                    return current

                labels = {"true": "恢复全部同步", "partial": "阻止全量同步（软限）", "false": "禁用所有同步（硬限）"}
                print(f"[api_monitor] 用量 {cnt}/{hard} (软限{soft}) → {labels.get(desired, desired)}")

                if row:
                    row.value = desired
                else:
                    session.add(Config(type_="knowledge_sync_enabled", value=desired,
                                       brief="API限额自动管控"))
                session.commit()
                return desired
            finally:
                session.close()
        except Exception:
            return "true"

    def snapshot(self, day: str = "") -> dict:
        """Return stats + auto-re-enable sync if under daily limit."""

        # Flush pending batch first
        self._flush_batch()

        from base.config.service import is_sync_enabled, is_full_sync_enabled

        today = day or _bj_now().strftime("%Y-%m-%d")

        # 每次 snapshot 都检查并自动调整同步状态（恢复/降级）
        try:
            state = self._ensure_state()
        except Exception:
            state = "true"

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
            "disabled": not is_sync_enabled(),
            "partial": is_sync_enabled() and not is_full_sync_enabled(),
            "sync_state": state,
        }

    @staticmethod
    def _query_stats_for_day(day: str) -> dict:
        """Query API call stats from MySQL for a specific day (YYYY-MM-DD, 北京时间)."""
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
