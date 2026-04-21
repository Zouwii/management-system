"""统计：季度工时、软件开发任务计数"""

from flask import request

from services.project_task_service import count_software_dev_tasks_in_config_last_year_service
from services.workhour_aggregate_service import (
    executor_all_quarter_workhours_db_service,
    executor_quarter_workhours_db_service,
    team_quarter_workhours_db_service,
    workdays_in_range_service,
)


def register(bp, ok, fail):
    @bp.route("/stats/workdays", methods=["POST"])
    def stats_workdays():
        try:
            payload = request.get_json(silent=True) or {}
            result = workdays_in_range_service(payload)
            if result.get("success"):
                return ok(result.get("data") or {})
            return fail(result.get("error", "workdays aggregate failed"), code=400, data=result.get("data"))
        except Exception as e:
            return fail(str(e), code=500, data={})

    @bp.route("/stats/executor_quarter_workhours", methods=["POST"])
    def stats_executor_quarter_workhours():
        try:
            payload = request.get_json(silent=True) or {}
            result = executor_quarter_workhours_db_service(payload)
            if result.get("success"):
                return ok(result.get("data") or {})
            return fail(result.get("error", "quarter aggregate failed"), code=400, data=result.get("data"))
        except Exception as e:
            return fail(str(e), code=500, data={})

    @bp.route("/stats/executor_all_quarter_workhours", methods=["POST"])
    def stats_executor_all_quarter_workhours():
        try:
            payload = request.get_json(silent=True) or {}
            result = executor_all_quarter_workhours_db_service(payload)
            if result.get("success"):
                return ok(result.get("data") or {})
            return fail(result.get("error", "executor all quarter aggregate failed"), code=400, data=result.get("data"))
        except Exception as e:
            return fail(str(e), code=500, data={})

    @bp.route("/stats/software_dev_count_last_year", methods=["POST"])
    def stats_software_dev_count_last_year():
        try:
            payload = request.get_json(silent=True) or {}
            result = count_software_dev_tasks_in_config_last_year_service(payload)
            if result.get("success"):
                return ok(result.get("data") or {})
            return fail(
                result.get("error", "count failed"),
                code=400,
                data=result.get("data") or {},
            )
        except Exception as e:
            return fail(str(e), code=500, data={})

    @bp.route("/stats/team_quarter_workhours", methods=["POST"])
    def stats_team_quarter_workhours():
        try:
            payload = request.get_json(silent=True) or {}
            result = team_quarter_workhours_db_service(payload)
            if result.get("success"):
                return ok(result.get("data") or {})
            return fail(result.get("error", "team quarter aggregate failed"), code=400, data=result.get("data") or {})
        except Exception as e:
            return fail(str(e), code=500, data={})
