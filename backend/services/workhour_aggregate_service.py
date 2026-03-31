"""
按执行者在服务端循环拉任务详情并汇总工时（单次 HTTP，避免浏览器 F12 出现大量请求）。
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_

from db.engine import SessionLocal
from db.orm import ProjectTask, ProjectTaskDetail, ProjectTaskOverdueDetail
from services.project_task_service import query_project_tasks_service, query_user_tasks_service
from services.workhour_util import parse_workhour_from_task_dict
from services.config_service import get_time_range_service

DEFAULT_SCENARIO_FIELD_CONFIG_ID = "647854bcd999c893061ef8b5"


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
    if not executor_id or not project_id:
        return {"success": False, "error": "missing executorId or projectId", "data": {}}

    tr = get_time_range_service() or {}
    start_time = tr.get("start_time", "")
    end_time = tr.get("end_time", "")

    session = SessionLocal()
    try:
        # B 表：季度工时候选（由同步阶段写入决定）
        b_rows: List[Tuple[str, Optional[float]]] = (
            session.query(ProjectTaskDetail.task_id, ProjectTaskDetail.work_hour)
            .filter(ProjectTaskDetail.project_id == project_id)
            .filter(ProjectTaskDetail.query_user_id == executor_id)
            .all()
        )

        # C 表：季度逾期明细（不按区间过滤，由同步阶段/落库决定）
        c_rows: List[Tuple[str, Optional[float]]] = (
            session.query(ProjectTaskOverdueDetail.task_id, ProjectTaskOverdueDetail.work_hour)
            .filter(ProjectTaskOverdueDetail.project_id == project_id)
            .filter(ProjectTaskOverdueDetail.query_user_id == executor_id)
            .all()
        )

        overdue_task_ids = {str(tid) for tid, _ in c_rows if tid is not None}
        all_task_ids = {str(tid) for tid, _ in b_rows if tid is not None} | overdue_task_ids

        # A 表只用于把 task_id 转中文 content（不参与统计口径）
        content_map: Dict[str, str] = {}
        if all_task_ids:
            a_rows = (
                session.query(ProjectTask.task_id, ProjectTask.content)
                .filter(ProjectTask.project_id == project_id)
                .filter(ProjectTask.task_id.in_(list(all_task_ids)))
                .all()
            )
            for tid, content in a_rows:
                if tid is not None:
                    content_map[str(tid)] = str(content or "")
    finally:
        session.close()

    # 计算汇总 + 生成明细并集（B+C）
    overdue_total = 0.0
    overdue_count = 0
    overdue_hour_map: Dict[str, Optional[float]] = {}
    for task_id, wh in c_rows:
        tid = str(task_id)
        overdue_hour_map[tid] = wh
        overdue_count += 1
        if wh is not None and isinstance(wh, (int, float)) and wh == wh:
            overdue_total += float(wh)

    total = 0.0
    task_count = 0
    breakdown: List[Dict[str, Any]] = []

    # 先输出 B 的行（按 B 表顺序），对 C 里的任务标记逾期并显示 C 的 work_hour
    for task_id, wh in b_rows:
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
                "work_hour": show_wh,
                "is_overdue": is_overdue,
            }
        )

    # 再补上：B 中不存在但 C 中存在的逾期任务（保证逾期表不空）
    b_task_ids = {str(tid) for tid, _ in b_rows if tid is not None}
    for tid in overdue_task_ids:
        if tid in b_task_ids:
            continue
        task_count += 1
        show_wh = overdue_hour_map.get(tid)
        breakdown.append(
            {
                "taskId": tid,
                "content": content_map.get(tid, tid),
                "work_hour": show_wh,
                "is_overdue": True,
            }
        )

    total = round(total * 100) / 100
    overdue_total = round(overdue_total * 100) / 100

    return {
        "success": True,
        "data": {
            "quarter_work_hour": total,
            "quarter_overdue_work_hour": overdue_total,
            "executor_id": executor_id,
            "project_id": project_id,
            "task_count": task_count,
            "overdue_task_count": overdue_count,
            "breakdown": breakdown,
            "time_range": {"start_time": start_time, "end_time": end_time},
        },
    }
