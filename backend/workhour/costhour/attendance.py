"""员工出勤表（加班、请假、法定带薪假）持久化存取。"""

from datetime import datetime, timezone

from base.db import get_session
from base.db.orm import MemberAttendance


def _quarter_from_start(start_time: str) -> tuple[int, int]:
    """从 start_time 字符串（如 2026-01-01T00:00:00）提取年份和季度。

    Returns:
        (year, quarter) 元组，quarter 为 1-4。
    """
    try:
        dt = datetime.fromisoformat(start_time)
    except (ValueError, TypeError):
        now = datetime.now(timezone.utc)
        return now.year, (now.month - 1) // 3 + 1
    year = dt.year
    quarter = (dt.month - 1) // 3 + 1
    if quarter < 1:
        quarter = 1
    if quarter > 4:
        quarter = 4
    return year, quarter


def get_attendance_service(payload: dict) -> dict:
    """读取指定季度所有用户的出勤调整记录。

    Args:
        payload: { start_time: str }

    Returns:
        { success: bool, data: { records: [{user_id, user_name, team_id,
           overtime_days, leave_days, statutory_holiday_days, effective_work_days,
           year, quarter}] }, error: str | None }
    """
    start_time = str(payload.get("start_time", ""))
    year, quarter = _quarter_from_start(start_time)

    session = get_session()
    try:
        rows = (
            session.query(MemberAttendance)
            .filter(
                MemberAttendance.year == year,
                MemberAttendance.quarter == quarter,
            )
            .all()
        )
        records = [
            {
                "user_id": r.user_id,
                "user_name": r.user_name,
                "team_id": r.team_id,
                "overtime_days": r.overtime_days,
                "leave_days": r.leave_days,
                "statutory_holiday_days": r.statutory_holiday_days,
                "effective_work_days": r.effective_work_days,
                "year": r.year,
                "quarter": r.quarter,
            }
            for r in rows
        ]
        return {"success": True, "data": {"records": records, "year": year, "quarter": quarter}}
    except Exception as e:
        return {"success": False, "error": str(e), "data": {}}
    finally:
        session.close()


def save_attendance_service(payload: dict) -> dict:
    """保存/更新指定季度一批用户的出勤调整记录。

    Args:
        payload: {
            start_time: str,
            records: [{ user_id, user_name, team_id, overtime_days,
                        leave_days, statutory_holiday_days, effective_work_days }]
        }

    Returns:
        { success: bool, data: { saved_count: int }, error: str | None }
    """
    start_time = str(payload.get("start_time", ""))
    records = payload.get("records", [])
    if not isinstance(records, list) or not records:
        return {"success": False, "error": "records is empty or invalid", "data": {}}

    year, quarter = _quarter_from_start(start_time)

    session = get_session()
    try:
        saved = 0
        now = datetime.now(timezone.utc)
        for record in records:
            user_id = str(record.get("user_id", "")).strip()
            if not user_id:
                continue

            existing = (
                session.query(MemberAttendance)
                .filter(
                    MemberAttendance.user_id == user_id,
                    MemberAttendance.year == year,
                    MemberAttendance.quarter == quarter,
                )
                .first()
            )

            if existing:
                existing.overtime_days = float(record.get("overtime_days", 0) or 0)
                existing.leave_days = float(record.get("leave_days", 0) or 0)
                existing.statutory_holiday_days = float(record.get("statutory_holiday_days", 0) or 0)
                existing.effective_work_days = float(record.get("effective_work_days", 0) or 0)
                existing.user_name = str(record.get("user_name", existing.user_name))
                existing.team_id = str(record.get("team_id", "")) if record.get("team_id") is not None else existing.team_id
                existing.updated_at = now
            else:
                session.add(
                    MemberAttendance(
                        user_id=user_id,
                        user_name=str(record.get("user_name", "")),
                        team_id=str(record.get("team_id", "")) if record.get("team_id") is not None else None,
                        year=year,
                        quarter=quarter,
                        overtime_days=float(record.get("overtime_days", 0) or 0),
                        leave_days=float(record.get("leave_days", 0) or 0),
                        statutory_holiday_days=float(record.get("statutory_holiday_days", 0) or 0),
                        effective_work_days=float(record.get("effective_work_days", 0) or 0),
                        created_at=now,
                        updated_at=now,
                    )
                )
            saved += 1

        session.commit()
        return {"success": True, "data": {"saved_count": saved, "year": year, "quarter": quarter}}
    except Exception as e:
        session.rollback()
        return {"success": False, "error": str(e), "data": {}}
    finally:
        session.close()
