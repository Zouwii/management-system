"""工作日耗时统计 — 三个 API 路由"""

from flask import request

from workhour.costhour.service import (
    workday_costhour_team_summary_service,
    workday_costhour_department_aggregate_service,
    workday_costhour_task_status_detail_service,
    workday_costhour_team_project_detail_service,
)


def register(bp, ok, fail):
    @bp.route("/stats/workday_costhour/team_summary", methods=["POST"])
    def stats_workday_costhour_team_summary():
        try:
            payload = request.get_json(silent=True) or {}
            result = workday_costhour_team_summary_service(payload)
            if result.get("success"):
                return ok(result.get("data") or {})
            return fail(result.get("error", "team summary aggregate failed"), code=400, data=result.get("data"))
        except Exception as e:
            return fail(str(e), code=500, data={})

    @bp.route("/stats/workday_costhour/department_aggregate", methods=["POST"])
    def stats_workday_costhour_department_aggregate():
        try:
            payload = request.get_json(silent=True) or {}
            result = workday_costhour_department_aggregate_service(payload)
            if result.get("success"):
                return ok(result.get("data") or {})
            return fail(result.get("error", "department aggregate failed"), code=400, data=result.get("data"))
        except Exception as e:
            return fail(str(e), code=500, data={})

    @bp.route("/stats/workday_costhour/task_status_detail", methods=["POST"])
    def stats_workday_costhour_task_status_detail():
        try:
            payload = request.get_json(silent=True) or {}
            result = workday_costhour_task_status_detail_service(payload)
            if result.get("success"):
                return ok(result.get("data") or {})
            return fail(result.get("error", "task status detail aggregate failed"), code=400, data=result.get("data"))
        except Exception as e:
            return fail(str(e), code=500, data={})

    @bp.route("/stats/workday_costhour/team_project_detail", methods=["POST"])
    def stats_workday_costhour_team_project_detail():
        try:
            payload = request.get_json(silent=True) or {}
            result = workday_costhour_team_project_detail_service(payload)
            if result.get("success"):
                return ok(result.get("data") or {})
            return fail(result.get("error", "team project detail failed"), code=400, data=result.get("data"))
        except Exception as e:
            return fail(str(e), code=500, data={})
