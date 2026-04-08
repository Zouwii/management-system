"""
按执行者在服务端循环拉任务详情并汇总工时（单次 HTTP，避免浏览器 F12 出现大量请求）。
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import chinese_calendar as cn_cal

from sqlalchemy import and_

from db.engine import SessionLocal
from db.orm import ProjectTask, ProjectTaskDetail, ProjectTaskOverdueDetail
from services.project_task_service import query_project_tasks_service, query_user_tasks_service
from services.workhour_util import parse_workhour_from_task_dict

DEFAULT_SCENARIO_FIELD_CONFIG_ID = "647854bcd999c893061ef8b5"
HOURS_PER_DAY = 8.0
SH_TZ = ZoneInfo("Asia/Shanghai")


def _field_id(payload: Dict[str, Any]) -> str:
    return str(
        payload.get("workHourFieldId")
        or os.getenv("TB_TOOL_BT_WORKHOUR_FIELD_ID")
        or os.getenv("TB_TOOL_B1_WORKHOUR_FIELD_ID")
        or "64c8cad8485fb3987a5521b8"
)


def _task_scope_rows(
    rows: Any,
    scenario_id: str,
    executor_id: str,
) -> List[Dict[str, str]]:
    """列表里符合场景+执行者的任务，带列表接口返回的标题（与前端下拉中文一致）。"""
    if not isinstance(rows, list):
        return []
    seen = set()
    out: List[Dict[str, str]] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        sid = str(r.get("scenariofieldconfigId") or r.get("scenarioFieldConfigId") or "")
        if sid != scenario_id:
            continue
        if str(r.get("executorId") or "") != str(executor_id):
            continue
        tid = str(r.get("taskId") or "").strip()
        if not tid or tid in seen:
            continue
        seen.add(tid)
        title = str(r.get("content") or "").strip()
        out.append({"task_id": tid, "list_content": title})
    return out


def _parse_detail_item(ding: Any) -> Optional[Dict[str, Any]]:
    if isinstance(ding, list) and ding:
        x = ding[0] if isinstance(ding[0], dict) else None
        return x
    if isinstance(ding, dict):
        return ding
    return None


def executor_quarter_workhours_db_service(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    从数据库汇总“季度工时 / 季度逾期”：
    - quarter_work_hour：B 表（project_task_details）工时总和
    - quarter_overdue_work_hour：C 表（project_task_overdue_details）工时总和

    说明：按 project_id + executor_id（query_user_id）统计，不再 join A 表。
    """
    payload = payload or {}
    t_all = time.perf_counter()
    executor_id = str(payload.get("executorId") or payload.get("executorid") or "").strip()
    project_id = str(payload.get("projectId") or payload.get("projectid") or "").strip()
    start_raw = payload.get("start_time")
    end_raw = payload.get("end_time")
    if not executor_id or not project_id:
        return {"success": False, "error": "missing executorId or projectId", "data": {}}

    def _to_utc_dt(v: Any) -> Optional[datetime]:
        s = str(v or "").strip()
        if not s:
            return None
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(s)
        except Exception:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt

    start_dt = _to_utc_dt(start_raw)
    end_dt = _to_utc_dt(end_raw)
    if not start_dt or not end_dt:
        return {"success": False, "error": "missing or invalid start_time/end_time", "data": {}}
    if start_dt > end_dt:
        return {"success": False, "error": "start_time must be <= end_time", "data": {}}

    t_query = time.perf_counter()
    session = SessionLocal()
    try:
        # B 表：按 payload 时间窗过滤（通过 A 表 due_date 关联）
        b_rows: List[Tuple[str, Optional[float], Optional[int], Optional[int]]] = (
            session.query(
                ProjectTaskDetail.task_id,
                ProjectTaskDetail.work_hour,
                ProjectTaskDetail.business_type,
                ProjectTaskDetail.task_flow_status_id,
            )
            .join(
                ProjectTask,
                and_(
                    ProjectTask.project_id == ProjectTaskDetail.project_id,
                    ProjectTask.task_id == ProjectTaskDetail.task_id,
                ),
            )
            .filter(ProjectTaskDetail.project_id == project_id)
            .filter(ProjectTaskDetail.query_user_id == executor_id)
            .filter(ProjectTask.scenario_field_config_id == DEFAULT_SCENARIO_FIELD_CONFIG_ID)
            .filter(ProjectTask.due_date != None)  # noqa: E711
            .filter(ProjectTask.due_date >= start_dt)
            .filter(ProjectTask.due_date <= end_dt)
            .all()
        )

        # C 表：同样按 payload 时间窗过滤（通过 A 表 due_date 关联）
        c_rows: List[Tuple[str, Optional[float], Optional[int], Optional[int]]] = (
            session.query(
                ProjectTaskOverdueDetail.task_id,
                ProjectTaskOverdueDetail.work_hour,
                ProjectTaskOverdueDetail.business_type,
                ProjectTaskOverdueDetail.task_flow_status_id,
            )
            .join(
                ProjectTask,
                and_(
                    ProjectTask.project_id == ProjectTaskOverdueDetail.project_id,
                    ProjectTask.task_id == ProjectTaskOverdueDetail.task_id,
                ),
            )
            .filter(ProjectTaskOverdueDetail.project_id == project_id)
            .filter(ProjectTaskOverdueDetail.query_user_id == executor_id)
            .filter(ProjectTask.scenario_field_config_id == DEFAULT_SCENARIO_FIELD_CONFIG_ID)
            .filter(ProjectTask.due_date != None)  # noqa: E711
            .filter(ProjectTask.due_date >= start_dt)
            .filter(ProjectTask.due_date <= end_dt)
            .all()
        )

        overdue_task_ids = {str(tid) for tid, _, _, _ in c_rows if tid is not None}
        all_task_ids = {str(tid) for tid, _, _, _ in b_rows if tid is not None} | overdue_task_ids

        # A 表用于补充展示字段：content / due_date（不参与统计口径）
        content_map: Dict[str, str] = {}
        due_map: Dict[str, str] = {}
        if all_task_ids:
            a_rows = (
                session.query(ProjectTask.task_id, ProjectTask.content, ProjectTask.due_date)
                .filter(ProjectTask.project_id == project_id)
                .filter(ProjectTask.task_id.in_(list(all_task_ids)))
                .all()
            )
            for tid, content, due_date in a_rows:
                if tid is not None:
                    content_map[str(tid)] = str(content or "")
                    if due_date is not None:
                        try:
                            due_map[str(tid)] = due_date.astimezone(timezone.utc).isoformat()
                        except Exception:
                            due_map[str(tid)] = str(due_date)
    finally:
        session.close()
    print(
        "ZHR TEMP [stats_executor_quarter] db_query cost_ms={} extra={}".format(
            round((time.perf_counter() - t_query) * 1000, 2),
            {"executorId": executor_id, "projectId": project_id, "b_count": len(b_rows), "c_count": len(c_rows)},
        )
    )

    # 计算汇总 + 生成明细并集（B+C）
    overdue_total = 0.0
    overdue_count = 0
    overdue_hour_map: Dict[str, Optional[float]] = {}
    business_type_map_c: Dict[str, Optional[int]] = {}
    task_flow_status_map_c: Dict[str, Optional[int]] = {}
    for task_id, wh, bt, tf in c_rows:
        tid = str(task_id)
        overdue_hour_map[tid] = wh
        business_type_map_c[tid] = bt
        task_flow_status_map_c[tid] = tf
        overdue_count += 1
        if wh is not None and isinstance(wh, (int, float)) and wh == wh:
            overdue_total += float(wh)

    total = 0.0
    task_count = 0
    breakdown: List[Dict[str, Any]] = []

    # 先输出 B 的行（按 B 表顺序），对 C 里的任务标记逾期并显示 C 的 work_hour
    for task_id, wh, bt, tf in b_rows:
        tid = str(task_id)
        is_overdue = tid in overdue_task_ids
        task_count += 1

        show_wh = overdue_hour_map[tid] if is_overdue else wh
        if show_wh is not None and isinstance(show_wh, (int, float)) and show_wh == show_wh and not is_overdue:
            total += float(show_wh)

        breakdown.append(
            {
                "taskId": tid,
                "content": content_map.get(tid, tid),
                "due_time": due_map.get(tid, ""),
                "work_hour": show_wh,
                "is_overdue": is_overdue,
                "business_type": bt if bt is not None else business_type_map_c.get(tid),
                "task_flow_status_id": tf if tf is not None else task_flow_status_map_c.get(tid),
            }
        )

    # 再补上：B 中不存在但 C 中存在的逾期任务（保证逾期表不空）
    b_task_ids = {str(tid) for tid, _, _, _ in b_rows if tid is not None}
    for tid in overdue_task_ids:
        if tid in b_task_ids:
            continue
        task_count += 1
        show_wh = overdue_hour_map.get(tid)
        breakdown.append(
            {
                "taskId": tid,
                "content": content_map.get(tid, tid),
                "due_time": due_map.get(tid, ""),
                "work_hour": show_wh,
                "is_overdue": True,
                "business_type": business_type_map_c.get(tid),
                "task_flow_status_id": task_flow_status_map_c.get(tid),
            }
        )

    total = round(total * 100) / 100
    overdue_total = round(overdue_total * 100) / 100

    out = {
        "success": True,
        "data": {
            "quarter_work_hour": total,
            "quarter_overdue_work_hour": overdue_total,
            "executor_id": executor_id,
            "project_id": project_id,
            "task_count": task_count,
            "overdue_task_count": overdue_count,
            "breakdown": breakdown,
            "time_range": {
                "start_time": start_dt.isoformat(),
                "end_time": end_dt.isoformat(),
            },
        },
    }
    print(
        "ZHR TEMP [stats_executor_quarter] total cost_ms={} extra={}".format(
            round((time.perf_counter() - t_all) * 1000, 2),
            {"executorId": executor_id, "projectId": project_id, "task_count": task_count, "overdue_task_count": overdue_count},
        )
    )
    return out


def workdays_in_range_service(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    统计指定时间窗内“法定工作日天数”。

    入参（可选）：
    - startDate / start_time
    - endDate / end_time
    - statutoryHolidays: [{"date":"YYYY-MM-DD"}] 或 ["YYYY-MM-DD", ...]
    - compensatoryDays: 调休天数（可选，默认 0）

    仅使用 payload.start/end（不再回退 config）。
    """
    payload = payload or {}
    start_raw = payload.get("startDate") or payload.get("start_time") or ""
    end_raw = payload.get("endDate") or payload.get("end_time") or ""

    def _to_utc_dt(v: Any) -> Optional[datetime]:
        s = str(v or "").strip()
        if not s:
            return None
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(s)
        except Exception:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt

    start_dt = _to_utc_dt(start_raw)
    end_dt = _to_utc_dt(end_raw)
    if not start_dt or not end_dt:
        return {"success": False, "error": "invalid start/end time", "data": {}}
    if start_dt > end_dt:
        return {"success": False, "error": "start_time must be <= end_time", "data": {}}

    holiday_raw = payload.get("statutoryHolidays") or []
    statutory_workday_raw = payload.get("statutoryWorkdays") or payload.get("workdays") or []
    holiday_set = set()
    statutory_workday_set = set()
    if isinstance(holiday_raw, list):
        for h in holiday_raw:
            if isinstance(h, dict):
                ds = str(h.get("date") or "").strip()
            else:
                ds = str(h or "").strip()
            if ds:
                holiday_set.add(ds[:10])
    if isinstance(statutory_workday_raw, list):
        for h in statutory_workday_raw:
            if isinstance(h, dict):
                ds = str(h.get("date") or "").strip()
            else:
                ds = str(h or "").strip()
            if ds:
                statutory_workday_set.add(ds[:10])

    try:
        compensatory_days = float(payload.get("compensatoryDays") or 0)
    except Exception:
        compensatory_days = 0.0

    # 按中国法定口径统计（Asia/Shanghai）：
    # - 使用 chinese_calendar 的 is_workday/is_holiday（含调休补班）
    # - 兼容前端额外传入 statutoryHolidays/statutoryWorkdays 进行覆盖
    start_local = start_dt.astimezone(SH_TZ)
    end_local = end_dt.astimezone(SH_TZ)
    cur = start_local.replace(hour=0, minute=0, second=0, microsecond=0)
    last = end_local.replace(hour=0, minute=0, second=0, microsecond=0)
    workdays = 0
    weekend_days = 0
    holiday_days = 0

    while cur <= last:
        d0 = cur.date()
        d = d0.isoformat()
        weekday = cur.weekday()  # Mon=0 ... Sun=6
        is_weekend = weekday >= 5

        # 先用法定日历判断
        is_work = bool(cn_cal.is_workday(d0))
        is_holi = bool(cn_cal.is_holiday(d0))
        # 再叠加调用方显式覆盖（便于临时修正）
        if d in statutory_workday_set:
            is_work = True
            is_holi = False
        if d in holiday_set:
            is_work = False
            is_holi = True

        if is_holi:
            holiday_days += 1
        elif not is_work and is_weekend:
            weekend_days += 1
        elif is_work:
            workdays += 1
        else:
            # 非节假日且非周末但也非工作日（理论上少见），视作非工作日
            pass
        cur += timedelta(days=1)

    adjusted_days = max(float(workdays) - compensatory_days, 0.0)
    return {
        "success": True,
        "data": {
            "start_time": start_local.isoformat(),
            "end_time": end_local.isoformat(),
            "workday_count": round(workdays, 2),
            "holiday_count": holiday_days,
            "weekend_count": weekend_days,
            "compensatory_days": compensatory_days,
            "effective_workday_count": round(adjusted_days, 2),
            "effective_workhour": round(adjusted_days * HOURS_PER_DAY, 2),
            "hours_per_day": HOURS_PER_DAY,
            "timezone": "Asia/Shanghai",
            "calendar_source": "chinese_calendar",
        },
    }
