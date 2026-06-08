"""步骤1: TB 任务数据查询 + 工时统计。

直接复用 PersonalHours 的 executor_quarter_workhours_db_service，
确保数据口径与工时管理界面完全一致。
"""

from __future__ import annotations

from datetime import datetime, timezone, date, timedelta
from typing import Any, Dict, List, Optional

# ── 映射表（与前端 realQueryPersonalHours 完全一致）────────────────

TASK_NATURE_VALUE_ID_TO_CODE = {
    "69d4d037c253ef42e9c31b3a": 0,  # 自主型
    "69d4d037c253ef42e9c31b39": 1,  # 指派型
    "69d4d037c253ef42e9c31b3b": 2,  # 能力型
}

TASK_NATURE_CODE_TO_LABEL = {0: "自主型", 1: "指派型", 2: "能力型"}

TASK_FLOW_STATUS_TO_LABEL = {0: "创建中", 1: "未完成", 2: "待评审", 3: "评审中", 4: "已完成", 5: "搁置"}

BUSINESS_TYPE_TO_LABEL = {0: "产品", 1: "研发", 2: "订单"}


def _classify_task_nature(task_nature: Optional[str]) -> str:
    if not task_nature:
        return "无"
    s = str(task_nature).strip()
    code = TASK_NATURE_VALUE_ID_TO_CODE.get(s)
    if code is not None:
        return TASK_NATURE_CODE_TO_LABEL[code]
    if s in ("指派型", "自主型", "能力型"):
        return s
    return "无"


def _status_label(task_flow_status_id) -> str:
    try:
        return TASK_FLOW_STATUS_TO_LABEL.get(int(task_flow_status_id), "")
    except (TypeError, ValueError):
        return ""


def _business_type_label(business_type) -> str:
    try:
        return BUSINESS_TYPE_TO_LABEL.get(int(business_type), "无")
    except (TypeError, ValueError):
        return "无"


# ── 复用 PersonalHours 的服务 ──────────────────────────────────


def _get_project_id() -> str:
    from base.config.service import get_config_projectids
    projectids = get_config_projectids() or {}
    if isinstance(projectids, dict) and projectids:
        return str(next(iter(projectids.values())) or "").strip()
    return ""


def _get_time_range():
    from base.config.service import get_default_time_range_service
    tr = get_default_time_range_service() or {}
    if tr.get("success"):
        return str(tr.get("start_time", "")), str(tr.get("end_time", ""))
    return "", ""


def _get_coefficient(user_character: Optional[int]) -> float:
    from base.config.service import get_workhour_character_coefficients_service
    coeff_out = get_workhour_character_coefficients_service() or {}
    coeff_map = coeff_out.get("workhour_character_coefficients") or {}
    if user_character is not None:
        return float(coeff_map.get(str(user_character), 1.0) or 1.0)
    return 1.0


def _get_workday_count(start: str, end: str) -> float:
    from workhour.personal.aggregate import workdays_in_range_service
    wd_out = workdays_in_range_service({"start_time": start, "end_time": end, "compensatoryDays": 0}) or {}
    return float((wd_out.get("data") or {}).get("workday_count") or 0.0)


# ── 工具函数 ────────────────────────────────────────────────────


def _current_quarter_range() -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    return _quarter_range(f"{now.year}Q{(now.month - 1) // 3 + 1}")


def _quarter_range(quarter: str) -> tuple[str, str]:
    """'2026Q2' → ('2026-04-01T00:00:00', '2026-06-30T23:59:59')."""
    import re
    m = re.match(r"(\d{4})Q([1-4])", quarter)
    if m:
        y, q = int(m.group(1)), int(m.group(2))
    else:
        now = datetime.now(timezone.utc)
        y, q = now.year, (now.month - 1) // 3 + 1
    start_month = (q - 1) * 3 + 1
    end_month = start_month + 3
    start = f"{y}-{start_month:02d}-01T00:00:00"
    if end_month > 12:
        end = f"{y + 1}-01-01T00:00:00"
    else:
        end = f"{y}-{end_month:02d}-01T00:00:00"
    end = _end_of_day_before(end)
    return start, end


def _end_of_day_before(next_start: str) -> str:
    """'2026-07-01T00:00:00' → '2026-06-30T23:59:59'."""
    try:
        d = date.fromisoformat(next_start[:10])
        return (d - timedelta(days=1)).isoformat() + "T23:59:59"
    except Exception:
        return next_start


def _quarter_label(start: str) -> str:
    try:
        y, m = int(start[:4]), int(start[5:7])
        return f"{y}Q{(m - 1) // 3 + 1}"
    except Exception:
        return ""


def _parse_date(s: str):
    try:
        return date.fromisoformat(s[:10])
    except Exception:
        return None


def _empty_stats(quarter: str, start: str, end: str) -> dict:
    return {
        "quarter": quarter,
        "total_tasks": 0, "done_count": 0, "overdue_count": 0,
        "total_work_hours": 0, "completed_work_hours": 0,
        "quarter_work_hour": 0, "quarter_completed_work_hour": 0,
        "quarter_overdue_work_hour": 0, "filled_cost_hour_sum": 0,
        "assigned_pct": 0, "autonomous_pct": 0, "capability_pct": 0,
        "coefficient": 1.0, "workday_count": 0, "expected_effective_days": 0,
        "passed_workdays": 0, "expected_hours_by_today": 0,
        "taskDistribution": {}, "statusBreakdown": {}, "natureDistribution": {},
    }


# ── 主查询 ─────────────────────────────────────────────────────


def fetch_tasks(
    quarter: str = "",
    owner_key: Optional[str] = None,
    project_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """拉取用户在季度内的 TB 任务数据。

    直接调用 executor_quarter_workhours_db_service，
    确保与工时管理界面数据口径完全一致。
    """
    from workhour.personal.aggregate import executor_quarter_workhours_db_service
    from base.db.engine import SessionLocal
    from base.db.orm import ProjectTask, ProjectTaskDetail, UserCharacter

    if quarter:
        start, end = _quarter_range(quarter)
    else:
        start, end = _current_quarter_range()
        quarter = _quarter_label(start)

    project_id = _get_project_id()
    if not project_id:
        return {"tasks": [], "stats": _empty_stats(quarter, start, end)}

    svc_result = executor_quarter_workhours_db_service({
        "executorId": owner_key or "",
        "projectId": project_id,
        "start_time": start,
        "end_time": end,
    })

    if not svc_result.get("success"):
        return {"tasks": [], "stats": _empty_stats(quarter, start, end)}

    svc_data = svc_result.get("data", {})
    breakdown = svc_data.get("breakdown", [])

    tasks = []
    done_count = 0
    overdue_count = 0
    total_wh = 0.0
    completed_wh = 0.0
    work_types: Dict[str, int] = {"指派型": 0, "自主型": 0, "能力型": 0, "无": 0}

    # 分布统计
    type_dist: Dict[str, dict] = {}
    status_dist: Dict[str, dict] = {}
    nature_dist: Dict[str, dict] = {}

    for row in breakdown:
        nature = _classify_task_nature(row.get("task_nature"))
        status = _status_label(row.get("task_flow_status_id"))
        tp = _business_type_label(row.get("business_type"))
        wh_val = float(row.get("work_hour") or 0)

        work_types[nature] += 1
        total_wh += wh_val
        if status == "已完成":
            done_count += 1
            completed_wh += wh_val
        if row.get("is_overdue"):
            overdue_count += 1

        # 累积分布
        type_dist.setdefault(tp, {"count": 0, "hours": 0.0})
        type_dist[tp]["count"] += 1
        type_dist[tp]["hours"] += wh_val

        status_dist.setdefault(status or "未知", {"count": 0, "hours": 0.0})
        status_dist[status or "未知"]["count"] += 1
        status_dist[status or "未知"]["hours"] += wh_val

        nature_dist.setdefault(nature, {"count": 0, "hours": 0.0})
        nature_dist[nature]["count"] += 1
        nature_dist[nature]["hours"] += wh_val

        tasks.append({
            "taskId": row.get("taskId", ""),
            "title": row.get("content", ""),
            "status": status,
            "taskNature": nature,
            "type": _business_type_label(row.get("business_type")),
            "workHour": wh_val,
            "isOverdue": row.get("is_overdue", False),
            "dueDate": str(row.get("due_time", "")),
            "parentTaskId": str(row.get("parent_task_id", "")).strip(),
        })

    # 补兄弟任务和任务描述
    parent_ids = {t["parentTaskId"] for t in tasks if t["parentTaskId"]}
    task_id_set = {t["taskId"] for t in tasks}
    sibling_map: Dict[str, list] = {}
    note_map: Dict[str, str] = {}
    if parent_ids:
        db2 = SessionLocal()
        try:
            # 走 project_task_details.parent_task_id 查同父任务
            siblings = (
                db2.query(ProjectTaskDetail.task_id, ProjectTaskDetail.parent_task_id, ProjectTaskDetail.content)
                .filter(ProjectTaskDetail.parent_task_id.in_(parent_ids))
                .all()
            )
            for sid, spid, s_content in siblings:
                if spid:
                    sibling_map.setdefault(str(spid).strip(), []).append({
                        "taskId": sid,
                        "title": s_content or "",
                    })
                if sid in task_id_set:
                    note_map[sid] = ""
            # 补 note 从 project_tasks
            notes = (
                db2.query(ProjectTask.task_id, ProjectTask.note)
                .filter(ProjectTask.task_id.in_(task_id_set))
                .all()
            )
            for tid, note in notes:
                note_map[tid] = str(note or "").strip()
            db2.close()
        except Exception:
            pass

    for t in tasks:
        pid = t["parentTaskId"]
        # 兄弟任务：排除自己
        all_sibs = sibling_map.get(pid, [])
        t["siblings"] = [s for s in all_sibs if s["taskId"] != t["taskId"]] if pid else []
        t["description"] = note_map.get(t["taskId"], "")

    # 提取任务描述和产出（从新增的列直接读，不需要解析 JSON）
    desc_map: Dict[str, str] = {}
    output_map: Dict[str, str] = {}
    if task_id_set:
        db3 = SessionLocal()
        try:
            cf_rows = (
                db3.query(ProjectTaskDetail.task_id, ProjectTaskDetail.requirement_desc, ProjectTaskDetail.task_outputs)
                .filter(ProjectTaskDetail.task_id.in_(task_id_set))
                .all()
            )
            for tid, desc, outputs in cf_rows:
                if desc:
                    desc_map[tid] = str(desc)
                if outputs:
                    output_map[tid] = str(outputs)
            db3.close()
        except Exception:
            pass

    for t in tasks:
        tid = t["taskId"]
        if not t["description"]:
            t["description"] = desc_map.get(tid, "")
        t["outputs"] = output_map.get(tid, "")

    db = SessionLocal()
    try:
        user_character = None
        if owner_key:
            uc = db.query(UserCharacter.character).filter(UserCharacter.user_id == owner_key).first()
            if uc and uc[0] is not None:
                user_character = int(uc[0])
        coefficient = _get_coefficient(user_character)
    finally:
        db.close()

    workday_count = _get_workday_count(start, end)
    today = date.today()
    end_date = _parse_date(end)
    effective_end = end_date if end_date and end_date < today else today
    passed_workdays = _get_workday_count(start, effective_end.isoformat() + "T23:59:59")

    total = len(tasks)
    stats = {
        "quarter": quarter,
        "total_tasks": total,
        "done_count": done_count,
        "overdue_count": overdue_count,
        "total_work_hours": round(total_wh, 1),
        "completed_work_hours": round(completed_wh, 1),
        "quarter_work_hour": round(svc_data.get("quarter_work_hour", 0), 1),
        "quarter_completed_work_hour": round(svc_data.get("quarter_completed_work_hour", 0), 1),
        "quarter_overdue_work_hour": round(svc_data.get("quarter_overdue_work_hour", 0), 1),
        "filled_cost_hour_sum": round(svc_data.get("filled_cost_hour_sum", 0), 1),
        "assigned_pct": round(work_types.get("指派型", 0) / max(total, 1) * 100, 1),
        "autonomous_pct": round(work_types.get("自主型", 0) / max(total, 1) * 100, 1),
        "capability_pct": round(work_types.get("能力型", 0) / max(total, 1) * 100, 1),
        "coefficient": coefficient,
        "workday_count": workday_count,
        "expected_effective_days": round(workday_count * coefficient, 2),
        "passed_workdays": passed_workdays,
        "expected_hours_by_today": round(passed_workdays * coefficient, 2),
        "taskDistribution": {k: round(v["hours"], 1) for k, v in type_dist.items()},
        "statusBreakdown": {k: {"count": v["count"], "hours": round(v["hours"], 1), "pct": round(v["hours"] / max(total_wh, 0.01) * 100, 1)} for k, v in status_dist.items()},
        "natureDistribution": {k: {"count": v["count"], "hours": round(v["hours"], 1), "pct": round(v["hours"] / max(total_wh, 0.01) * 100, 1)} for k, v in nature_dist.items()},
    }

    return {"tasks": tasks, "stats": stats}
