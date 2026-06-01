"""步骤1: TB 任务数据查询 + 工时统计。

按季度和用户拉取 project_tasks + project_task_details，
统计指派/自主/能力分布、完成/逾期数量。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# task_nature 钉钉自定义字段值 ID → 工时类型
NATURE_VALUE_ID_TO_NAME = {
    "69d4d037c253ef42e9c31b3a": "自主型",
    "69d4d037c253ef42e9c31b39": "指派型",
    "69d4d037c253ef42e9c31b3b": "能力型",
}


def _classify_task_nature(task_nature: Optional[str]) -> str:
    """将 task_nature 字段值映射为可读的工时类型."""
    if not task_nature:
        return "其他"
    tn = str(task_nature).strip()
    return NATURE_VALUE_ID_TO_NAME.get(tn, tn if tn in ("指派型", "自主型", "能力型") else "其他")


def _quarter_range(quarter: str) -> tuple[str, str]:
    """Parse '2026Q2' → ('2026-04-01', '2026-07-01')."""
    import re

    m = re.match(r"(\d{4})Q([1-4])", quarter)
    if not m:
        year = datetime.now(timezone.utc).year
        month = datetime.now(timezone.utc).month
        q = (month - 1) // 3 + 1
    else:
        year, q = int(m.group(1)), int(m.group(2))

    start_month = (q - 1) * 3 + 1
    end_month = start_month + 3
    start = f"{year}-{start_month:02d}-01"
    if end_month > 12:
        end = f"{year + 1}-01-01"
    else:
        end = f"{year}-{end_month:02d}-01"
    return start, end


def fetch_tasks(
    quarter: str = "",
    owner_key: Optional[str] = None,
    project_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Fetch tasks for a user in a given quarter.

    Args:
        quarter: e.g. '2026Q2'. Defaults to current quarter.
        owner_key: executor_id filter. None = all users.
        project_ids: optional project filter.
    """
    from db.engine import SessionLocal
    from db.orm import ProjectTask, ProjectTaskDetail

    if not quarter:
        quarter = _current_quarter()
    start, end = _quarter_range(quarter)

    db = SessionLocal()
    try:
        # Base query: tasks with due_date in quarter
        q = (
            db.query(ProjectTask)
            .join(ProjectTaskDetail, ProjectTask.task_id == ProjectTaskDetail.task_id)
            .filter(
                ProjectTask.is_deleted == False,
                ProjectTaskDetail.due_date >= start,
                ProjectTaskDetail.due_date < end,
            )
        )
        if owner_key:
            q = q.filter(ProjectTask.executor_id == owner_key)
        if project_ids:
            q = q.filter(ProjectTask.project_id.in_(project_ids))

        rows = q.all()
        if not rows:
            return {"tasks": [], "stats": _empty_stats()}

        task_ids = [t.task_id for t in rows]
        detail_map = {t.task_id: t for t in rows}  # ProjectTaskDetail via join
        # Re-query details separately for cleaner access
        details = (
            db.query(ProjectTaskDetail)
            .filter(ProjectTaskDetail.task_id.in_(task_ids))
            .all()
        )
        detail_map2 = {d.task_id: d for d in details}

        tasks = []
        done_count = 0
        overdue_count = 0
        total_work_hours = 0.0
        work_types: Dict[str, int] = {"指派型": 0, "自主型": 0, "能力型": 0, "其他": 0}

        for t in rows:
            d = detail_map2.get(t.task_id)
            if t.is_done:
                done_count += 1
            if d and d.is_overdue:
                overdue_count += 1
            nature = _classify_task_nature(d.task_nature if d else None)
            work_types[nature] += 1
            wh = d.work_hour if d else None
            if wh:
                total_work_hours += wh

            tasks.append({
                "taskId": t.task_id,
                "title": t.content or "",
                "progress": t.progress or 0,
                "isOverdue": d.is_overdue if d else False,
                "isDone": t.is_done,
                "workHour": d.work_hour if d else None,
                "taskNature": nature,
                "businessType": d.business_type if d else None,
                "dueDate": d.due_date.isoformat() if d and d.due_date else (t.due_date.isoformat() if t and t.due_date else None),
            })

        total = len(tasks)
        stats = {
            "quarter": quarter,
            "total_tasks": total,
            "done_count": done_count,
            "overdue_count": overdue_count,
            "total_work_hours": round(total_work_hours, 1),
            "assigned_pct": round(work_types.get("指派型", 0) / max(total, 1) * 100, 1),
            "autonomous_pct": round(work_types.get("自主型", 0) / max(total, 1) * 100, 1),
            "capability_pct": round(work_types.get("能力型", 0) / max(total, 1) * 100, 1),
        }

        return {"tasks": tasks, "stats": stats}
    finally:
        db.close()


def _current_quarter() -> str:
    now = datetime.now(timezone.utc)
    q = (now.month - 1) // 3 + 1
    return f"{now.year}Q{q}"


def _empty_stats() -> dict:
    return {
        "quarter": _current_quarter(),
        "total_tasks": 0,
        "done_count": 0,
        "overdue_count": 0,
        "total_work_hours": 0,
        "assigned_pct": 0,
        "autonomous_pct": 0,
        "capability_pct": 0,
    }
