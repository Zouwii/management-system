"""
按执行者在服务端循环拉任务详情并汇总工时（单次 HTTP，避免浏览器 F12 出现大量请求）。
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import chinese_calendar as cn_cal

from sqlalchemy import and_, func

from base.db.engine import SessionLocal
from base.db.orm import Config as DbConfig
from base.db.orm import (
    ProgramIssue,
    ProgramIssueDetail,
    ProjectTask,
    ProjectTaskDetail,
    ProjectTaskOverdueDetail,
    UserCharacter as DbUserCharacter,
)
from base.projects.task_service import query_project_tasks_service, query_user_tasks_service
from base.config.service import get_workhour_character_coefficients_service
from workhour.personal.util import parse_workhour_from_task_dict
from base.config.member_visibility import should_hide_member_in_selector

DEFAULT_SCENARIO_FIELD_CONFIG_ID = "647854bcd999c893061ef8b5"
ISSUE_SCENARIO_FIELD_CONFIG_ID = "665ee4b95b46f34b3e0463a8"
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
            # datetime-local（无时区）按 Asia/Shanghai 本地时间解释，再转 UTC
            dt = dt.replace(tzinfo=SH_TZ).astimezone(timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt

    start_dt = _to_utc_dt(start_raw)
    end_dt = _to_utc_dt(end_raw)
    if not start_dt or not end_dt:
        return {"success": False, "error": "missing or invalid start_time/end_time", "data": {}}
    if start_dt > end_dt:
        return {"success": False, "error": "start_time must be <= end_time", "data": {}}

    print(
        "[executor_quarter_workhours] request executor_id={} project_id={} start_utc={} end_utc={}".format(
            executor_id,
            project_id,
            start_dt.isoformat(),
            end_dt.isoformat(),
        )
    )

    session = SessionLocal()
    try:
        # 诊断：基于 B 表自身字段统计过滤去向
        b_join_total = (
            session.query(func.count())
            .select_from(ProjectTaskDetail)
            .filter(ProjectTaskDetail.project_id == project_id)
            .filter(ProjectTaskDetail.query_user_id == executor_id)
            .scalar()
            or 0
        )
        b_not_dev = (
            session.query(func.count())
            .select_from(ProjectTaskDetail)
            .filter(ProjectTaskDetail.project_id == project_id)
            .filter(ProjectTaskDetail.query_user_id == executor_id)
            .filter(ProjectTaskDetail.scenario_field_config_id != DEFAULT_SCENARIO_FIELD_CONFIG_ID)
            .scalar()
            or 0
        )
        b_due_null = (
            session.query(func.count())
            .select_from(ProjectTaskDetail)
            .filter(ProjectTaskDetail.project_id == project_id)
            .filter(ProjectTaskDetail.query_user_id == executor_id)
            .filter(ProjectTaskDetail.scenario_field_config_id == DEFAULT_SCENARIO_FIELD_CONFIG_ID)
            .filter(ProjectTaskDetail.due_date == None)  # noqa: E711
            .scalar()
            or 0
        )
        b_due_before = (
            session.query(func.count())
            .select_from(ProjectTaskDetail)
            .filter(ProjectTaskDetail.project_id == project_id)
            .filter(ProjectTaskDetail.query_user_id == executor_id)
            .filter(ProjectTaskDetail.scenario_field_config_id == DEFAULT_SCENARIO_FIELD_CONFIG_ID)
            .filter(ProjectTaskDetail.due_date != None)  # noqa: E711
            .filter(ProjectTaskDetail.due_date < start_dt)
            .scalar()
            or 0
        )
        b_due_after = (
            session.query(func.count())
            .select_from(ProjectTaskDetail)
            .filter(ProjectTaskDetail.project_id == project_id)
            .filter(ProjectTaskDetail.query_user_id == executor_id)
            .filter(ProjectTaskDetail.scenario_field_config_id == DEFAULT_SCENARIO_FIELD_CONFIG_ID)
            .filter(ProjectTaskDetail.due_date != None)  # noqa: E711
            .filter(ProjectTaskDetail.due_date > end_dt)
            .scalar()
            or 0
        )

        # B 表：按 payload 时间窗过滤（通过 A 表 due_date 关联）
        b_rows: List[
            Tuple[str, Optional[float], Optional[int], Optional[int], Optional[str], Optional[str], Optional[float]]
        ] = (
            session.query(
                ProjectTaskDetail.task_id,
                ProjectTaskDetail.work_hour,
                ProjectTaskDetail.business_type,
                ProjectTaskDetail.task_flow_status_id,
                ProjectTaskDetail.parent_task_id,
                ProjectTaskDetail.task_nature,
                ProjectTaskDetail.workday_costhour,
            )
            .filter(ProjectTaskDetail.project_id == project_id)
            .filter(ProjectTaskDetail.query_user_id == executor_id)
            .filter(ProjectTaskDetail.scenario_field_config_id == DEFAULT_SCENARIO_FIELD_CONFIG_ID)
            .filter(ProjectTaskDetail.due_date != None)  # noqa: E711
            .filter(ProjectTaskDetail.due_date >= start_dt)
            .filter(ProjectTaskDetail.due_date <= end_dt)
            .all()
        )
        print(
            "[executor_quarter_workhours] b_filter join_total={} in_window={} filtered_not_dev={} filtered_due_null={} filtered_due_before={} filtered_due_after={}".format(
                int(b_join_total),
                len(b_rows),
                int(b_not_dev),
                int(b_due_null),
                int(b_due_before),
                int(b_due_after),
            )
        )

        # C 表：当前逾期快照口径（不按 payload 时间窗过滤）
        c_rows: List[Tuple[str, Optional[float], Optional[int], Optional[int], Optional[str], Optional[float]]] = (
            session.query(
                ProjectTaskOverdueDetail.task_id,
                ProjectTaskOverdueDetail.work_hour,
                ProjectTaskOverdueDetail.business_type,
                ProjectTaskOverdueDetail.task_flow_status_id,
                ProjectTaskOverdueDetail.task_nature,
                ProjectTaskOverdueDetail.workday_costhour,
            )
            .filter(ProjectTaskOverdueDetail.project_id == project_id)
            .filter(ProjectTaskOverdueDetail.query_user_id == executor_id)
            .filter(ProjectTaskOverdueDetail.scenario_field_config_id == DEFAULT_SCENARIO_FIELD_CONFIG_ID)
            .all()
        )
        print(
            "[executor_quarter_workhours] c_snapshot_count={} (not filtered by start/end)".format(
                len(c_rows)
            )
        )

        # B2 表：问题处理明细（按 payload 时间窗过滤，基于 program_issue.due_date）
        issue_rows: List[Tuple[str, Optional[float], Optional[float], Optional[datetime]]] = (
            session.query(
                ProgramIssueDetail.task_id,
                ProgramIssueDetail.work_hour,
                ProgramIssueDetail.workday_costhour,
                ProgramIssue.due_date,
            )
            .join(
                ProgramIssue,
                and_(
                    ProgramIssue.project_id == ProgramIssueDetail.project_id,
                    ProgramIssue.task_id == ProgramIssueDetail.task_id,
                ),
            )
            .filter(ProgramIssueDetail.project_id == project_id)
            .filter(ProgramIssueDetail.query_user_id == executor_id)
            .filter(ProgramIssue.scenario_field_config_id == ISSUE_SCENARIO_FIELD_CONFIG_ID)
            .filter(ProgramIssue.due_date != None)  # noqa: E711
            .filter(ProgramIssue.due_date >= start_dt)
            .filter(ProgramIssue.due_date <= end_dt)
            .all()
        )
        print(
            "[executor_quarter_workhours] issue_in_window_count={}".format(
                len(issue_rows)
            )
        )

        overdue_task_ids = {str(tid) for tid, _, _, _, _, _ in c_rows if tid is not None}

        # B/C 已冗余 content/due_date，不再依赖 A 映射展示
        b_meta_rows = (
            session.query(ProjectTaskDetail.task_id, ProjectTaskDetail.content, ProjectTaskDetail.due_date)
            .filter(ProjectTaskDetail.project_id == project_id)
            .filter(ProjectTaskDetail.query_user_id == executor_id)
            .filter(ProjectTaskDetail.scenario_field_config_id == DEFAULT_SCENARIO_FIELD_CONFIG_ID)
            .all()
        )
        c_meta_rows = (
            session.query(ProjectTaskOverdueDetail.task_id, ProjectTaskOverdueDetail.content, ProjectTaskOverdueDetail.due_date)
            .filter(ProjectTaskOverdueDetail.project_id == project_id)
            .filter(ProjectTaskOverdueDetail.query_user_id == executor_id)
            .filter(ProjectTaskOverdueDetail.scenario_field_config_id == DEFAULT_SCENARIO_FIELD_CONFIG_ID)
            .all()
        )
        content_map: Dict[str, str] = {}
        due_map: Dict[str, str] = {}
        for tid, content, due_date in list(b_meta_rows) + list(c_meta_rows):
            if tid is None:
                continue
            key = str(tid)
            if key not in content_map:
                content_map[key] = str(content or "")
            if key not in due_map and due_date is not None:
                try:
                    due_map[key] = due_date.astimezone(timezone.utc).isoformat()
                except Exception:
                    due_map[key] = str(due_date)
        print(
            "[executor_quarter_workhours] self_mapping from_b={} from_c={} merged_keys={}".format(
                len(b_meta_rows),
                len(c_meta_rows),
                len(content_map),
            )
        )
    finally:
        session.close()

    # 计算汇总 + 生成明细并集（B+C）
    overdue_total = 0.0
    overdue_count = 0
    overdue_hour_map: Dict[str, Optional[float]] = {}
    business_type_map_c: Dict[str, Optional[int]] = {}
    task_flow_status_map_c: Dict[str, Optional[int]] = {}
    task_nature_map_c: Dict[str, Optional[str]] = {}
    workday_costhour_map_c: Dict[str, Optional[int]] = {}
    for task_id, wh, bt, tf, tn, wdm in c_rows:
        tid = str(task_id)
        overdue_hour_map[tid] = wh
        business_type_map_c[tid] = bt
        task_flow_status_map_c[tid] = tf
        task_nature_map_c[tid] = tn
        workday_costhour_map_c[tid] = wdm
        overdue_count += 1
        if wh is not None and isinstance(wh, (int, float)) and wh == wh:
            overdue_total += float(wh)

    total = 0.0
    quarter_completed_work_hour = 0.0
    current_quarter_workday_costhour_sum = 0.0
    task_count = 0
    breakdown: List[Dict[str, Any]] = []

    # 先输出 B 的行（按 B 表顺序），对 C 里的任务标记逾期并显示 C 的 work_hour
    parent_task_id_map_b: Dict[str, str] = {}
    for task_id, wh, bt, tf, parent_tid, tn, wdm in b_rows:
        tid = str(task_id)
        parent_task_id_map_b[tid] = str(parent_tid or "").strip()
        is_overdue = tid in overdue_task_ids
        task_count += 1

        show_wh = overdue_hour_map[tid] if is_overdue else wh
        if show_wh is not None and isinstance(show_wh, (int, float)) and show_wh == show_wh and not is_overdue:
            total += float(show_wh)
            if int(tf or -1) == 4:
                quarter_completed_work_hour += float(show_wh)

        resolved_workday_costhour = wdm if wdm is not None else workday_costhour_map_c.get(tid)
        if (
            not is_overdue
            and resolved_workday_costhour is not None
            and isinstance(resolved_workday_costhour, (int, float))
            and resolved_workday_costhour == resolved_workday_costhour
        ):
            current_quarter_workday_costhour_sum += float(resolved_workday_costhour)

        breakdown.append(
            {
                "taskId": tid,
                "content": content_map.get(tid, tid),
                "due_time": due_map.get(tid, ""),
                "work_hour": show_wh,
                "is_overdue": is_overdue,
                "business_type": bt if bt is not None else business_type_map_c.get(tid),
                "task_flow_status_id": tf if tf is not None else task_flow_status_map_c.get(tid),
                "parent_task_id": parent_task_id_map_b.get(tid, ""),
                "task_nature": tn if tn is not None else task_nature_map_c.get(tid),
                "workday_costhour": resolved_workday_costhour,
            }
        )

    # 再补上：B 中不存在但 C 中存在的逾期任务（保证逾期表不空）
    b_task_ids = {str(tid) for tid, _, _, _, _, _, _ in b_rows if tid is not None}
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
                "parent_task_id": parent_task_id_map_b.get(tid, ""),
                "task_nature": task_nature_map_c.get(tid),
                "workday_costhour": workday_costhour_map_c.get(tid),
            }
        )

    total = round(total * 100) / 100
    quarter_completed_work_hour = round(quarter_completed_work_hour * 100) / 100
    overdue_total = round(overdue_total * 100) / 100

    current_quarter_workday_costhour_sum = round(current_quarter_workday_costhour_sum * 100) / 100

    issue_total = 0.0
    issue_count = 0
    issue_monthly_bucket: Dict[str, float] = {}
    for _task_id, _wh, issue_costhour, issue_due_date in issue_rows:
        issue_count += 1
        if issue_costhour is not None and isinstance(issue_costhour, (int, float)) and issue_costhour == issue_costhour:
            issue_val = float(issue_costhour)
            issue_total += issue_val
            if issue_due_date is not None:
                try:
                    local_dt = issue_due_date.astimezone(SH_TZ)
                except Exception:
                    local_dt = issue_due_date
                month_label = f"{int(getattr(local_dt, 'month', 0) or 0)}月"
                if month_label != "0月":
                    issue_monthly_bucket[month_label] = float(issue_monthly_bucket.get(month_label, 0.0)) + issue_val
    issue_total = round(issue_total * 100) / 100
    issue_monthly_cost_hours = [
        {"month": month, "hours": round(float(hours) * 100) / 100}
        for month, hours in sorted(
            issue_monthly_bucket.items(),
            key=lambda item: int(str(item[0]).replace("月", "") or 0),
        )
    ]
    # 饼图口径统一为“工作日耗时”：软件开发工时 = 当前季度工作日耗时已填写和。
    software_dev_total = current_quarter_workday_costhour_sum

    out = {
        "success": True,
        "data": {
            "quarter_work_hour": total,
            "quarter_completed_work_hour": quarter_completed_work_hour,
            "filled_cost_hour_sum": current_quarter_workday_costhour_sum,
            "quarter_overdue_work_hour": overdue_total,
            "software_work_cost_hour": software_dev_total,
            "issue_work_cost_hour": issue_total,
            "issue_monthly_cost_hours": issue_monthly_cost_hours,
            "executor_id": executor_id,
            "project_id": project_id,
            "task_count": task_count,
            "overdue_task_count": overdue_count,
            "issue_task_count": issue_count,
            "breakdown": breakdown,
            "time_range": {
                "start_time": start_dt.isoformat(),
                "end_time": end_dt.isoformat(),
            },
        },
    }
    print(
        "[executor_quarter_workhours] result task_count={} overdue_task_count={} quarter_work_hour={} quarter_overdue_work_hour={}".format(
            int(out["data"].get("task_count") or 0),
            int(out["data"].get("overdue_task_count") or 0),
            float(out["data"].get("quarter_work_hour") or 0.0),
            float(out["data"].get("quarter_overdue_work_hour") or 0.0),
        )
    )
    return out


def executor_all_quarter_workhours_db_service(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    按执行者列表聚合季度工时（单次 HTTP），用于 target=ALL 场景减少前端并发请求数量。
    """
    payload = payload or {}
    executor_ids_raw = payload.get("executorIds") or payload.get("executor_ids") or []
    if not isinstance(executor_ids_raw, list):
        return {"success": False, "error": "executorIds must be a list", "data": {}}
    executor_ids = [str(x or "").strip() for x in executor_ids_raw if str(x or "").strip()]
    executor_ids = list(dict.fromkeys(executor_ids))
    if not executor_ids:
        return {
            "success": True,
            "data": {
                "quarter_work_hour": 0.0,
                "quarter_completed_work_hour": 0.0,
                "filled_cost_hour_sum": 0.0,
                "quarter_overdue_work_hour": 0.0,
                "software_work_cost_hour": 0.0,
                "issue_work_cost_hour": 0.0,
                "issue_monthly_cost_hours": [],
                "task_count": 0,
                "overdue_task_count": 0,
                "issue_task_count": 0,
                "breakdown": [],
                "executor_count": 0,
                "executor_ids": [],
            },
        }

    project_id = str(payload.get("projectId") or payload.get("projectid") or "").strip()
    start_time = payload.get("start_time")
    end_time = payload.get("end_time")
    if not project_id or not start_time or not end_time:
        return {"success": False, "error": "missing projectId/start_time/end_time", "data": {}}

    merged: Dict[str, Dict[str, Any]] = {}
    quarter_total = 0.0
    quarter_completed_total = 0.0
    filled_cost_hour_sum = 0.0
    overdue_total = 0.0
    software_dev_total = 0.0
    issue_total = 0.0
    issue_monthly_bucket: Dict[str, float] = {}
    overdue_task_count = 0
    issue_task_count = 0

    for executor_id in executor_ids:
        one = executor_quarter_workhours_db_service(
            {
                "executorId": executor_id,
                "projectId": project_id,
                "start_time": start_time,
                "end_time": end_time,
            }
        )
        if not one.get("success"):
            return one
        data = one.get("data") or {}
        quarter_total += float(data.get("quarter_work_hour") or 0.0)
        quarter_completed_total += float(data.get("quarter_completed_work_hour") or 0.0)
        filled_cost_hour_sum += float(data.get("filled_cost_hour_sum") or 0.0)
        overdue_total += float(data.get("quarter_overdue_work_hour") or 0.0)
        software_dev_total += float(data.get("software_work_cost_hour") or 0.0)
        issue_total += float(data.get("issue_work_cost_hour") or 0.0)
        for row in (data.get("issue_monthly_cost_hours") or []):
            month = str((row or {}).get("month") or "").strip()
            if not month:
                continue
            hours = float((row or {}).get("hours") or 0.0)
            issue_monthly_bucket[month] = float(issue_monthly_bucket.get(month, 0.0)) + hours
        overdue_task_count += int(data.get("overdue_task_count") or 0)
        issue_task_count += int(data.get("issue_task_count") or 0)
        for row in (data.get("breakdown") or []):
            task_id = str((row or {}).get("taskId") or "").strip()
            if not task_id:
                continue
            raw_hour = (row or {}).get("work_hour")
            hour = float(raw_hour) if isinstance(raw_hour, (int, float)) and raw_hour == raw_hour else 0.0
            prev = merged.get(task_id)
            if not prev:
                prev = dict(row or {})
                prev["work_hour"] = 0.0
            prev["work_hour"] = float(prev.get("work_hour") or 0.0) + hour
            if (row or {}).get("is_overdue"):
                prev["is_overdue"] = True
            if (row or {}).get("content"):
                prev["content"] = row.get("content")
            if (row or {}).get("due_time"):
                prev["due_time"] = row.get("due_time")
            if (row or {}).get("parent_task_id") is not None:
                prev["parent_task_id"] = row.get("parent_task_id")
            if (row or {}).get("business_type") is not None:
                prev["business_type"] = row.get("business_type")
            if (row or {}).get("task_flow_status_id") is not None:
                prev["task_flow_status_id"] = row.get("task_flow_status_id")
            merged[task_id] = prev

    return {
        "success": True,
        "data": {
            "quarter_work_hour": round(quarter_total * 100) / 100,
            "quarter_completed_work_hour": round(quarter_completed_total * 100) / 100,
            "filled_cost_hour_sum": round(filled_cost_hour_sum * 100) / 100,
            "quarter_overdue_work_hour": round(overdue_total * 100) / 100,
            "software_work_cost_hour": round(software_dev_total * 100) / 100,
            "issue_work_cost_hour": round(issue_total * 100) / 100,
            "issue_monthly_cost_hours": [
                {"month": month, "hours": round(float(hours) * 100) / 100}
                for month, hours in sorted(
                    issue_monthly_bucket.items(),
                    key=lambda item: int(str(item[0]).replace("月", "") or 0),
                )
            ],
            "task_count": len(merged),
            "overdue_task_count": overdue_task_count,
            "issue_task_count": issue_task_count,
            "breakdown": list(merged.values()),
            "executor_count": len(executor_ids),
            "executor_ids": executor_ids,
        },
    }


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
            # datetime-local（无时区）按 Asia/Shanghai 本地时间解释，再转 UTC
            dt = dt.replace(tzinfo=SH_TZ).astimezone(timezone.utc)
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
    monthly_workdays: Dict[str, int] = {}

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
            month_label = f"{int(cur.month)}月"
            monthly_workdays[month_label] = int(monthly_workdays.get(month_label, 0)) + 1
        else:
            # 非节假日且非周末但也非工作日（理论上少见），视作非工作日
            pass
        cur += timedelta(days=1)

    adjusted_days = max(float(workdays) - compensatory_days, 0.0)
    result = {
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
            "month_workdays": [
                {"month": month, "day": day}
                for month, day in sorted(monthly_workdays.items(), key=lambda x: int(str(x[0]).replace("月", "")))
            ],
            "month_day": dict(monthly_workdays),
        },
    }
    return result


def _to_character(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return int(default)
        return int(value)
    except Exception:
        return int(default)


def _team_name_from_team_id(team_id_value: Any) -> str:
    if team_id_value is None:
        return "未分组"
    val = str(team_id_value).strip()
    if val == "0":
        return "导航组"
    if val == "1":
        return "对接组"
    return "未分组"


def _member_role_label_from_user_character(character_value: Any) -> str:
    c = _to_character(character_value, default=1)
    if c == 0:
        return "组长"
    if c == 1:
        return "软件开发工程师"
    if c == 2:
        return "软件应用工程师"
    if c == 3:
        return "应用工程师"
    if c == 4:
        return "算法工程师"
    return "软件开发工程师"


def team_quarter_workhours_db_service(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    团队维度季度工时聚合（单接口返回 team-detail 需要的数据）：
    - rows：每个成员的工时明细聚合
    - memberOptions：前端筛选下拉
    - lastUpdatedAt：页面右上角“最后同步”
    """
    payload = payload or {}
    team_id = str(payload.get("teamId") or payload.get("team_id") or "").strip()
    project_id = str(payload.get("projectId") or payload.get("project_id") or "").strip()
    start_raw = payload.get("start_time")
    end_raw = payload.get("end_time")
    exclude_character_zero = str(payload.get("exclude_character_zero", "true")).strip().lower() not in {"0", "false", "no"}
    if team_id not in {"0", "1"}:
        return {"success": False, "error": "invalid teamId", "data": {}}
    if not project_id:
        return {"success": False, "error": "missing projectId", "data": {}}

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
            dt = dt.replace(tzinfo=SH_TZ).astimezone(timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt

    start_dt = _to_utc_dt(start_raw)
    end_dt = _to_utc_dt(end_raw)
    if not start_dt or not end_dt:
        return {"success": False, "error": "missing or invalid start_time/end_time", "data": {}}
    if start_dt > end_dt:
        return {"success": False, "error": "start_time must be <= end_time", "data": {}}

    coeff_out = get_workhour_character_coefficients_service() or {}
    coeff_map = coeff_out.get("workhour_character_coefficients") or {}
    wd_out = workdays_in_range_service(
        {
            "start_time": start_dt.isoformat(),
            "end_time": end_dt.isoformat(),
            "compensatoryDays": 0,
        }
    ) or {}
    quarter_expected_days = float(((wd_out.get("data") or {}).get("effective_workday_count")) or 0.0)

    session = SessionLocal()
    try:
        members = (
            session.query(DbUserCharacter)
            .filter(DbUserCharacter.team_id == team_id)
            .order_by(DbUserCharacter.user_id.asc())
            .all()
        )

        rows: List[Dict[str, Any]] = []
        member_options: List[Dict[str, Any]] = []
        for m in members:
            uid = str(getattr(m, "user_id", "") or "").strip()
            if not uid:
                continue
            member_character = _to_character(getattr(m, "character", None), default=0)
            # 仅隐藏“管理员”：character=0 且同时 nav+servo lead。
            if exclude_character_zero:
                is_nav_lead = bool(getattr(m, "is_nav_lead", False))
                is_servo_lead = bool(getattr(m, "is_servo_lead", False))
                if should_hide_member_in_selector(
                    {
                        "character": member_character,
                        "isNavLead": is_nav_lead,
                        "isServoLead": is_servo_lead,
                    }
                ):
                    continue
            name = str(getattr(m, "name", "") or uid)
            coefficient = float(coeff_map.get(str(member_character), 1.0) or 1.0)
            expected_effective_hours = quarter_expected_days * coefficient

            b_base = (
                session.query(ProjectTaskDetail)
                .join(
                    ProjectTask,
                    and_(
                        ProjectTask.project_id == ProjectTaskDetail.project_id,
                        ProjectTask.task_id == ProjectTaskDetail.task_id,
                    ),
                )
                .filter(ProjectTaskDetail.query_user_id == uid)
                .filter(ProjectTaskDetail.project_id == project_id)
                .filter(ProjectTask.due_date != None)  # noqa: E711
                .filter(ProjectTask.due_date >= start_dt)
                .filter(ProjectTask.due_date <= end_dt)
            )
            scheduled_total = float(
                b_base.with_entities(func.coalesce(func.sum(ProjectTaskDetail.work_hour), 0.0)).scalar() or 0.0
            )
            completed_total = float(
                b_base.filter(ProjectTaskDetail.task_flow_status_id == 4)
                .with_entities(func.coalesce(func.sum(ProjectTaskDetail.work_hour), 0.0))
                .scalar()
                or 0.0
            )

            c_base = (
                session.query(ProjectTaskOverdueDetail)
                .join(
                    ProjectTask,
                    and_(
                        ProjectTask.project_id == ProjectTaskOverdueDetail.project_id,
                        ProjectTask.task_id == ProjectTaskOverdueDetail.task_id,
                    ),
                )
                .filter(ProjectTaskOverdueDetail.query_user_id == uid)
                .filter(ProjectTaskOverdueDetail.project_id == project_id)
            )
            overdue_effective_total = float(
                c_base.with_entities(func.coalesce(func.sum(ProjectTaskOverdueDetail.work_hour), 0.0)).scalar() or 0.0
            )
            overdue_completed_total = float(
                c_base.filter(ProjectTaskOverdueDetail.task_flow_status_id == 4)
                .with_entities(func.coalesce(func.sum(ProjectTaskOverdueDetail.work_hour), 0.0))
                .scalar()
                or 0.0
            )

            allocation_delta = scheduled_total - expected_effective_hours
            completion_delta = completed_total - expected_effective_hours
            rows.append(
                {
                    "userId": uid,
                    "name": name,
                    "role": _member_role_label_from_user_character(member_character),
                    "quarterExpectedHours": round(expected_effective_hours, 2),
                    "workdayCount": round(quarter_expected_days, 2),
                    "character": member_character,
                    "coefficient": coefficient,
                    "scheduledHours": round(scheduled_total, 2),
                    "completedHours": round(completed_total, 2),
                    "overdueEffectiveHours": round(overdue_effective_total, 2),
                    "overdueCompletedHours": round(overdue_completed_total, 2),
                    "allocationDelta": round(allocation_delta, 2),
                    "completionDelta": round(completion_delta, 2),
                    "hours": round(scheduled_total, 2),
                }
            )
            member_options.append(
                {
                    "id": uid,
                    "name": name,
                    "team": _team_name_from_team_id(getattr(m, "team_id", None)),
                    "teamId": str(getattr(m, "team_id", "") or ""),
                }
            )

        last_row = session.query(DbConfig).filter(DbConfig.type_ == "last_update_time").first()
        last_updated_at = str(getattr(last_row, "value", "") or "")
        return {
            "success": True,
            "data": {
                "rows": rows,
                "memberOptions": member_options,
                "lastUpdatedAt": last_updated_at,
                "teamId": team_id,
                "projectId": project_id,
                "timeRange": {
                    "start_time": start_dt.isoformat(),
                    "end_time": end_dt.isoformat(),
                },
            },
        }
    finally:
        session.close()
