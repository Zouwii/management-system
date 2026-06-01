"""步骤1: 拉取任务数据."""

from __future__ import annotations

from flask import request


def register(bp, ok, fail):
    @bp.route("/ai/task-analysis/fetch-tasks", methods=["POST"])
    def ai_task_analysis_fetch_tasks():
        """Fetch TB tasks for a quarter + user. Returns tasks and stats.

        Body: { quarter?: "2026Q2", owner_key?: "...", project_ids?: [...] }
        """
        body = request.get_json(silent=True) or {}
        quarter = str(body.get("quarter") or "").strip()
        owner_key = str(body.get("owner_key") or "").strip() or None
        project_ids = body.get("project_ids") or None

        from ai.task_analysis.data import fetch_tasks

        try:
            result = fetch_tasks(quarter=quarter, owner_key=owner_key, project_ids=project_ids)
            return ok(result)
        except Exception as e:
            return fail(str(e), code=500)
