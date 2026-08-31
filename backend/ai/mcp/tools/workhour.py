"""Tool: get_workhour_summary — user's work hour summary for a date range."""

TASK_NATURE_LABELS = {
    "69d4d037c253ef42e9c31b3a": "zi-zhu-xing",
    "69d4d037c253ef42e9c31b39": "zhih-pai-xing",
    "69d4d037c253ef42e9c31b3b": "neng-li-xing",
}

TASK_FLOW_STATUS_LABELS = {
    0: "creating", 1: "unfinished", 2: "under review",
    3: "reviewing", 4: "completed", 5: "shelved",
}


def _status_label(status_id) -> str:
    try:
        return TASK_FLOW_STATUS_LABELS.get(int(status_id), "unknown")
    except (TypeError, ValueError):
        return "unknown"


def register_tool(mcp, resolve_user_fn):
    @mcp.tool()
    async def get_workhour_summary(
        start_date: str = "", end_date: str = "",
    ) -> dict:
        """Query current user's work hour summary for a date range.

        Args:
            start_date: Start date (YYYY-MM-DD), defaults to current quarter start
            end_date: End date (YYYY-MM-DD), defaults to current quarter end
        """
        uid, _ = resolve_user_fn()
        if not uid:
            return {"error": "No user identity"}

        if not start_date or not end_date:
            from base.config.service import get_default_time_range_service
            tr = get_default_time_range_service() or {}
            if tr.get("success"):
                start_date = str(tr.get("start_time", ""))[:10]
                end_date = str(tr.get("end_time", ""))[:10]

        if not start_date or not end_date:
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)
            q = (now.month - 1) // 3
            start_month = q * 3 + 1
            start_date = f"{now.year}-{start_month:02d}-01"
            end_month = start_month + 2
            last_day = [31, 30, 30, 31, 31, 30, 30, 31, 30, 31, 30, 31][end_month - 1]
            end_date = f"{now.year}-{end_month:02d}-{last_day}"

        from base.config.service import get_config_projectids
        projectids = get_config_projectids() or {}
        project_id = str(next(iter(projectids.values())) or "").strip() if projectids else ""
        if not project_id:
            return {"error": "projectId not configured"}

        from workhour.personal.aggregate import executor_quarter_workhours_db_service, workdays_in_range_service
        svc_result = executor_quarter_workhours_db_service({
            "executorId": uid,
            "projectId": project_id,
            "start_time": f"{start_date}T00:00:00",
            "end_time": f"{end_date}T23:59:59",
        })
        if not svc_result.get("success"):
            return {"error": svc_result.get("error", "workhour query failed")}

        data = svc_result.get("data", {})

        from base.config.service import get_workhour_role_coefficients_service
        from base.db.engine import SessionLocal
        from base.db.orm import UserCharacter as DbUserCharacter

        nature_dist: dict[str, dict] = {}
        status_dist: dict[str, dict] = {}
        for row in data.get("breakdown", []):
            raw_nature = str(row.get("task_nature") or "none")
            nature = TASK_NATURE_LABELS.get(raw_nature, raw_nature)
            status = _status_label(row.get("task_flow_status_id"))
            wh = float(row.get("work_hour") or 0)

            nature_dist.setdefault(nature, {"count": 0, "hours": 0.0})
            nature_dist[nature]["count"] += 1
            nature_dist[nature]["hours"] += round(wh, 1)

            status_dist.setdefault(status, {"count": 0, "hours": 0.0})
            status_dist[status]["count"] += 1
            status_dist[status]["hours"] += round(wh, 1)

        coefficient = 1.0
        db = SessionLocal()
        try:
            uc = db.query(DbUserCharacter.job_role_code).filter(DbUserCharacter.user_id == uid).first()
            if uc and uc[0] is not None:
                coeff_out = get_workhour_role_coefficients_service() or {}
                coeff_map = coeff_out.get("workhour_role_coefficients") or {}
                coefficient = float(coeff_map.get(str(uc[0]).strip().upper(), 1.0) or 1.0)
        finally:
            db.close()

        wd_result = workdays_in_range_service({
            "start_time": f"{start_date}T00:00:00",
            "end_time": f"{end_date}T23:59:59",
            "compensatoryDays": 0,
        })
        wd_data = (wd_result.get("data") or {}) if wd_result.get("success") else {}
        workday_count = float(wd_data.get("workday_count") or 0)
        expected_days = round(workday_count * coefficient, 2)

        total = data.get("task_count", 0)
        planned = round(data.get("quarter_work_hour", 0), 1)
        completed = round(data.get("quarter_completed_work_hour", 0), 1)
        overdue = round(data.get("quarter_overdue_work_hour", 0), 1)
        filled_cost = round(data.get("filled_cost_hour_sum", 0), 1)

        overdue_tasks = [
            {"taskId": r.get("taskId"), "title": r.get("content", ""), "work_hour": r.get("work_hour")}
            for r in data.get("breakdown", []) if r.get("is_overdue")
        ][:20]

        return {
            "time_range": {"start": start_date, "end": end_date},
            "project_id": project_id,
            "totals": {
                "task_count": total,
                "planned_hours": planned,
                "completed_hours": completed,
                "overdue_hours": overdue,
                "filled_cost_hours": filled_cost,
            },
            "capacity": {
                "workday_count": workday_count,
                "coefficient": coefficient,
                "expected_effective_days": expected_days,
                "planned_vs_expected": f"planned {planned}d / expected {expected_days}d",
            },
            "nature_distribution": {
                k: {
                    "count": v["count"],
                    "hours": v["hours"],
                    "pct": round(v["hours"] / max(planned, 0.01) * 100, 1),
                }
                for k, v in nature_dist.items()
            },
            "status_distribution": {
                k: {"count": v["count"], "hours": v["hours"]}
                for k, v in status_dist.items()
            },
            "overdue_tasks": overdue_tasks,
        }
