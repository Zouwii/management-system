"""DingTalk API call monitor — SQL-backed with in-memory rate limiting.

- Every API call is persisted to api_call_logs table.
- Batch flush: accumulates 50 entries before writing to DB.
- Aggregated stats queried from DB (today).
- 所有日期判断使用北京时间 (UTC+8)。
- 内存计数器实时拦截超限调用，不等待 DB 写入。
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


def _bj_today_str() -> str:
    """返回北京时间今天的日期字符串 YYYY-MM-DD"""
    return _bj_now().strftime("%Y-%m-%d")


class ApiCallMonitor:
    """Singleton monitor. DB-persisted with batch flush + in-memory rate limiting."""

    _instance: Optional["ApiCallMonitor"] = None
    _lock = threading.Lock()

    def __init__(self):
        self._started_at = time.time()
        self._batch: list = []   # pending batch for DB insert
        self._batch_lock = threading.Lock()
        self._last_record_at: float = time.time()
        # 内存计数器：当天调用次数 + 硬限阻断标记，避免等待 DB 写入
        self._today_str: str = _bj_today_str()
        self._mem_count: int = 0
        self._hard_blocked: bool = False
        self._bypass_depth: int = 0   # >0 时绕过限流（全量更新）
        self._count_lock = threading.Lock()

    @classmethod
    def get(cls) -> "ApiCallMonitor":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def check_allowed(self) -> bool:
        """实时检查是否允许发起新的钉钉 API 调用。硬限时返回 False。

        全量更新期间 (_bypass_depth > 0) 总是允许。
        """
        with self._count_lock:
            if self._bypass_depth > 0:
                return True
            # 日期切换：重置内存计数
            today = _bj_today_str()
            if self._today_str != today:
                self._today_str = today
                self._mem_count = 0
                self._hard_blocked = False
            if self._hard_blocked:
                return False
            if self._mem_count >= self._daily_limit():
                self._hard_blocked = True
                self._ensure_state()
                print(f"[api_monitor] HARD BLOCK: {self._mem_count}/{self._daily_limit()} calls reached, blocking further requests")
                return False
            return True

    def enter_bypass(self) -> None:
        """进入全量更新模式，绕过限流。"""
        with self._count_lock:
            self._bypass_depth += 1
            print(f"[api_monitor] bypass enabled (depth={self._bypass_depth})")

    def leave_bypass(self) -> None:
        """退出全量更新模式。"""
        with self._count_lock:
            self._bypass_depth = max(0, self._bypass_depth - 1)
            print(f"[api_monitor] bypass disabled (depth={self._bypass_depth})")

    def record(self, endpoint: str, status: int, latency_ms: int, error: str = "",
               source: str = ""):
        """Record a single API call — accumulate for batch flush (50条或60秒)."""
        # 更新内存计数
        with self._count_lock:
            today = _bj_today_str()
            if self._today_str != today:
                self._today_str = today
                self._mem_count = 0
                self._hard_blocked = False
            self._mem_count += 1

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
        """当日硬限额（100%）：临时调高到 100000"""
        return 100000

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
        """根据当日用量自动设置 daily_sync_enabled。

        硬限（100%）：写 'false'，is_sync_enabled() 返回 False，阻止所有同步。
        低于硬限：写 'true'，恢复同步。
        """
        cnt = self._today_count()
        hard = self._daily_limit()
        desired = "false" if cnt >= hard else "true"

        try:
            from base.db.engine import SessionLocal
            from base.db.orm import Config
            session = SessionLocal()
            try:
                row = session.query(Config).filter(Config.type_ == "daily_sync_enabled").first()
                current = str(row.value).strip().lower() if row else "true"
                if current == desired:
                    return current

                label = "禁用所有同步（硬限）" if desired == "false" else "恢复同步"
                print(f"[api_monitor] 用量 {cnt}/{hard} → {label}")

                if row:
                    row.value = desired
                else:
                    session.add(Config(type_="daily_sync_enabled", value=desired,
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

        from base.config.service import is_sync_enabled

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


def check_api_allowed() -> bool:
    """检查是否允许发起新的钉钉 API 调用。硬限时返回 False。"""
    return monitor.check_allowed()


def enter_full_sync_mode() -> None:
    """进入全量更新模式，绕过 API 限流。"""
    monitor.enter_bypass()


def leave_full_sync_mode() -> None:
    """退出全量更新模式。"""
    monitor.leave_bypass()
