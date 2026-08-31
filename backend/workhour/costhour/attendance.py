"""员工出勤表（加班、请假、法定带薪假）持久化存取。"""

from datetime import datetime, timezone

from base.db import get_session
from base.db.orm import MemberAttendance
from base.organization.service import list_scope_members
from base.organization.constants import stable_team_code


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
        { success: bool, data: { records: [{user_id, user_name, teamCode,
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
        saved = {str(r.user_id).strip(): r for r in rows}
        records = []
        # Always return the complete ATTENDANCE roster, including members
        # without a saved row for this quarter.
        for member in list_scope_members("ATTENDANCE"):
            user_id = str(member.get("userId") or "").strip()
            if not user_id:
                continue
            row = saved.get(user_id)
            records.append({
                "user_id": user_id,
                "user_name": member.get("userName") or user_id,
                "teamCode": member.get("teamCode") or "",
                "overtime_days": row.overtime_days if row else 0,
                "leave_days": row.leave_days if row else 0,
                "statutory_holiday_days": row.statutory_holiday_days if row else 0,
                "effective_work_days": row.effective_work_days if row else 0,
                "year": year,
                "quarter": quarter,
            })
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
            records: [{ user_id, overtime_days,
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
        roster = {
            str(member.get("userId") or "").strip(): member
            for member in list_scope_members("ATTENDANCE")
            if str(member.get("userId") or "").strip()
        }
        saved = 0
        now = datetime.now(timezone.utc)
        for record in records:
            user_id = str(record.get("user_id", "")).strip()
            member = roster.get(user_id)
            if not user_id or member is None:
                continue
            canonical_name = str(member.get("userName") or user_id)
            team_code = stable_team_code(member.get("teamCode"))

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
                existing.user_name = canonical_name
                existing.team_code = team_code or existing.team_code
                existing.updated_at = now
            else:
                session.add(
                    MemberAttendance(
                        user_id=user_id,
                        user_name=canonical_name,
                        team_code=team_code or None,
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
