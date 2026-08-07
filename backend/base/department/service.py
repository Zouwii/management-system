"""部门总览聚合服务。

模块划分：
  1. 基础数据    — 季度/项目ID/最后同步时间
  2. 工作日      — 法定工作日天数  → workdays_in_range_service
  3. 成员信息    — 人员列表        → user_character 表
  4. 工时数据    — 每人排期/逾期   → team_quarter_workhours_db_service(teamId=0) + teamId=1
  5. 绩效数据    — 每人绩效档位    → nav_perf_quarter_result / servo_perf_quarter_result
  6. 组装        — 按 userId 合并上述数据 → 统一 rows + stats
"""

from __future__ import annotations

import calendar
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Tuple

from base.config.service import get_default_time_range_service
from base.config.member_visibility import is_dual_team_admin
from base.db.engine import PerfSessionLocal, SessionLocal
from base.db.orm import NavPerfQuarterResult, ServoPerfQuarterResult, UserCharacter
from base.dingtalk_client import get_config_projectids
from workhour.personal.aggregate import team_quarter_workhours_db_service, workdays_in_range_service

_TEAM_LABEL = {"0": "导航组", "1": "对接组"}
_TEAM_KEY = {"0": "nav", "1": "servo"}

_ROLE_MAP = {
    0: "组长",
    1: "软件开发工程师",
    2: "软件应用工程师",
    3: "应用工程师",
    4: "算法工程师",
    5: "实习生",
}

def _get_role(character: int) -> str:
    return _ROLE_MAP.get(character, str(character))


# ═══════════════════════════════════════════
#  1. 基础数据：当前季度、项目 ID、最后同步时间
# ═══════════════════════════════════════════

def _current_quarter() -> Tuple[int, int]:
    """当前年份和季度，例如 (2026, 2)。"""
    today = date.today()
    return today.year, (today.month - 1) // 3 + 1


def _prev_quarter(year: int, quarter: int) -> Tuple[int, int]:
    """上一季度。Q1 → 上年 Q4。"""
    if quarter == 1:
        return year - 1, 4
    return year, quarter - 1


def _quarter_iso_range(year: int, quarter: int) -> Tuple[str, str]:
    """季度起止 ISO 时间，例如 ('2026-04-01T00:00:00+00:00', '2026-06-30T23:59:59+00:00')。"""
    start_month = (quarter - 1) * 3 + 1
    end_month = start_month + 2
    last_day = calendar.monthrange(year, end_month)[1]
    start = datetime(year, start_month, 1, 0, 0, 0, tzinfo=timezone.utc)
    end = datetime(year, end_month, last_day, 23, 59, 59, tzinfo=timezone.utc)
    return start.isoformat(), end.isoformat()


def _parse_date_range(start_date: str | None, end_date: str | None, fallback: Tuple[str, str]) -> Tuple[str, str]:
    """解析前端日期筛选，缺失或非法时回退当前季度范围。"""
    if not start_date or not end_date:
        return fallback

    def _parse(value: str, is_end: bool) -> datetime:
        text = str(value or "").strip()
        if not text:
            raise ValueError("empty date")
        if len(text) == 10:
            parsed = datetime.fromisoformat(text)
            return parsed.replace(
                hour=23 if is_end else 0,
                minute=59 if is_end else 0,
                second=59 if is_end else 0,
                microsecond=0,
                # 不设 tzinfo，由 workdays_in_range_service 按 Asia/Shanghai 本地时间解释
            )
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    try:
        start = _parse(start_date, False)
        end = _parse(end_date, True)
        if end < start:
            return fallback
        return start.isoformat(), end.isoformat()
    except Exception:
        return fallback


def _get_project_id() -> str:
    """从 ids.json 取第一个 project_id。"""
    pids = get_config_projectids()
    if isinstance(pids, dict) and pids:
        return str(next(iter(pids.values())) or "").strip()
    return ""


# ═══════════════════════════════════════════
#  2. 工作日：法定工作日天数
#     → workdays_in_range_service
# ═══════════════════════════════════════════

def _calc_workday_count(quarter_start: str, quarter_end: str) -> float:
    """计算季度内法定工作日天数（含调休）。"""
    out = workdays_in_range_service({
        "start_time": quarter_start,
        "end_time": quarter_end,
        "compensatoryDays": 0,
    })
    wd = (out or {}).get("data", {})
    return float(wd.get("workday_count") or wd.get("effective_workday_count") or 0)


# ═══════════════════════════════════════════
#  3. 成员信息：user_character 表
#     → 排除：character=9 或 (character=0 且同时是 nav+servo 组长)
#     → 规则复用 is_dual_team_admin
# ═══════════════════════════════════════════

def _fetch_members() -> List[Dict[str, Any]]:
    """查询全部可见成员（排除双组管理员）。"""
    session = SessionLocal()
    try:
        rows = session.query(UserCharacter).order_by(UserCharacter.user_id.asc()).all()
        members = []
        for r in rows:
            uid = str(getattr(r, "user_id", "") or "").strip()
            if not uid:
                continue
            tid = str(getattr(r, "team_id", "") or "").strip()
            # 算法组(team_id=2)不出现在部门总览中
            if tid == "2":
                continue
            char_val = int(getattr(r, "character", 0) or 0)

            # 排除双组管理员：character=9 或 (character=0 且同时 nav+servo 组长)
            if is_dual_team_admin({
                "character": char_val,
                "isNavLead": bool(getattr(r, "is_nav_lead", False)),
                "isServoLead": bool(getattr(r, "is_servo_lead", False)),
            }):
                continue

            members.append({
                "userId": uid,
                "userName": str(getattr(r, "name", "") or uid).strip() or uid,
                "teamKey": _TEAM_KEY.get(tid, tid),
                "team": _TEAM_LABEL.get(tid, tid or "未分组"),
                "character": char_val,
                "isTeamLead": str(getattr(r, "character", "")) in ("0", "9"),
            })
        return members
    finally:
        session.close()


# ═══════════════════════════════════════════
#  4. 工时数据：复用 team_quarter_workhours_db_service
#     → 分别调 teamId=0(导航组) + teamId=1(对接组)
#     → 包含组长，exclude_character_zero=false
# ═══════════════════════════════════════════

def _fetch_work_hours_map(project_id: str, quarter_start: str, quarter_end: str) -> Dict[str, Dict[str, float]]:
    """返回 {userId: {scheduledHours, completedHours, overdueHours, overdueCompletedHours, coefficient}}。"""
    hours_map: Dict[str, Dict[str, float]] = {}

    for team_id in ("0", "1"):
        result = team_quarter_workhours_db_service({
            "teamId": team_id,
            "projectId": project_id,
            "start_time": quarter_start,
            "end_time": quarter_end,
            "exclude_character_zero": "false",   # 包含组长
        })
        rows = (result.get("data", {}) or {}).get("rows", []) if result.get("success") else []

        for row in rows:
            uid = str(row.get("userId", ""))
            if not uid:
                continue
            hours_map[uid] = {
                "scheduledHours": float(row.get("scheduledHours", 0) or 0),
                "completedHours": float(row.get("completedHours", 0) or 0),
                "overdueHours": float(row.get("overdueEffectiveHours", 0) or 0),
                "overdueCompletedHours": float(row.get("overdueCompletedHours", 0) or 0),
                "coefficient": float(row.get("coefficient", 1) or 1),
            }

    return hours_map


# ═══════════════════════════════════════════
#  5. 绩效数据：nav_perf_quarter_result + servo_perf_quarter_result
#     → 只取 calc_status in (calculated, archived)
# ═══════════════════════════════════════════

def _fetch_perf_map(year: int, quarter: int) -> Dict[str, Dict[str, Any]]:
    """返回 {userId: {workHourScore, supervisorScore, overallScore, finalScore, companyScore, newCarryBalance, calcStatus}}。"""
    session = PerfSessionLocal()
    try:
        result: Dict[str, Dict[str, Any]] = {}
        for Model in (NavPerfQuarterResult, ServoPerfQuarterResult):
            rows = session.query(Model).filter(
                Model.year == year,
                Model.quarter == quarter,
                Model.calc_status.in_(["calculated", "archived"]),
            ).all()
            for r in rows:
                uid = str(r.user_id)
                result[uid] = {
                    "workHourScore": float(r.work_hour_score) if r.work_hour_score is not None else None,
                    "supervisorScore": float(r.supervisor_score) if r.supervisor_score is not None else None,
                    "overallScore": float(r.overall_score) if r.overall_score is not None else None,
                    "finalScore": float(r.final_score) if r.final_score is not None else None,
                    "companyScore": float(r.company_score) if r.company_score is not None else None,
                    "newCarryBalance": float(r.new_carry_balance) if r.new_carry_balance is not None else None,
                    "calcStatus": str(r.calc_status),
                }
        return result
    finally:
        session.close()


# ═══════════════════════════════════════════
#  6. 组装：按 userId 合并 成员 + 工时 + 绩效 → unified rows + stats
# ═══════════════════════════════════════════

def _assemble_response(
    members: List[Dict[str, Any]],
    hours_map: Dict[str, Dict[str, float]],
    prev_perf_map: Dict[str, Dict[str, Any]],
    curr_perf_map: Dict[str, Dict[str, Any]],
    year: int, quarter: int,
    perf_year: int, perf_quarter: int,
    workday_count: float,
    last_updated: str,
) -> Dict[str, Any]:
    """将三个数据源按 userId 对齐，产出一行一人 + 聚合统计。"""
    rows: List[Dict[str, Any]] = []
    nav_count = 0
    servo_count = 0
    total_hours = 0.0

    for m in members:
        uid = m["userId"]
        tk = m["teamKey"]
        if tk == "nav":
            nav_count += 1
        elif tk == "servo":
            servo_count += 1

        wh = hours_map.get(uid, {})
        prev_pf = prev_perf_map.get(uid, {})
        curr_pf = curr_perf_map.get(uid, {})

        sched = wh.get("scheduledHours", 0.0)
        od = wh.get("overdueHours", 0.0)
        coeff = wh.get("coefficient", 1.0)
        total_hours += sched + od

        # 应分配 = 工作日天数 × 个人系数（动态跟随日期区间）
        expected_effective = round(workday_count * coeff, 2)

        rows.append({
            "userId": uid,
            "userName": m["userName"],
            "team": m["team"],
            "teamKey": tk,
            "character": m["character"],
            "role": _get_role(m["character"]),
            "isTeamLead": m["isTeamLead"],
            # 工时
            "coefficient": coeff,
            "expectedEffectiveHours": expected_effective,
            "scheduledHours": sched,
            "completedHours": wh.get("completedHours", 0.0),
            "overdueHours": od,
            "overdueCompletedHours": wh.get("overdueCompletedHours", 0.0),
            # 绩效
            "prevFinalScore": prev_pf.get("finalScore"),
            "currentFinalScore": curr_pf.get("finalScore"),
            "workHourScore": prev_pf.get("workHourScore"),
            "supervisorScore": prev_pf.get("supervisorScore"),
            "overallScore": prev_pf.get("overallScore"),
            "companyScore": prev_pf.get("companyScore"),
            "newCarryBalance": prev_pf.get("newCarryBalance"),
            "calcStatus": prev_pf.get("calcStatus"),
        })

    final_scores = [r["prevFinalScore"] for r in rows if r["prevFinalScore"] is not None]
    avg_final = round(sum(final_scores) / len(final_scores), 2) if final_scores else 0.0

    return {
        "success": True,
        "data": {
            "lastUpdatedAt": last_updated,
            "quarter": {"year": year, "quarter": quarter},
            "perfQuarter": {"year": perf_year, "quarter": perf_quarter},
            "workdayCount": round(workday_count, 1),
            "stats": {
                "totalMembers": len(members),
                "navMembers": nav_count,
                "servoMembers": servo_count,
                "totalHours": round(total_hours, 2),
                "avgFinalScore": avg_final,
            },
            "rows": rows,
        },
    }


# ═══════════════════════════════════════════
#  主入口：按模块顺序调用，拼装后返回
# ═══════════════════════════════════════════

def department_overview_service(start_date: str | None = None, end_date: str | None = None) -> Dict[str, Any]:
    # 1. 基础数据
    year, quarter = _current_quarter()
    default_start, default_end = _quarter_iso_range(year, quarter)
    quarter_start, quarter_end = _parse_date_range(start_date, end_date, (default_start, default_end))
    perf_year, perf_quarter = _prev_quarter(year, quarter)
    project_id = _get_project_id()
    tr = get_default_time_range_service() or {}
    last_updated = str(tr.get("last_update_time") or "")

    # 2. 工作日
    workday_count = _calc_workday_count(quarter_start, quarter_end)

    # 3. 成员信息
    members = _fetch_members()

    # 4. 工时数据（当前季度）
    hours_map = _fetch_work_hours_map(project_id, quarter_start, quarter_end)

    # 5. 绩效数据（上一季度 + 本季度）
    prev_perf_map = _fetch_perf_map(perf_year, perf_quarter)
    curr_perf_map = _fetch_perf_map(year, quarter)

    # 6. 组装返回
    return _assemble_response(
        members, hours_map, prev_perf_map, curr_perf_map,
        year, quarter, perf_year, perf_quarter, workday_count, last_updated,
    )
