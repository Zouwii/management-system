"""工作日耗时统计 — 三个 API 路由"""

from flask import request

from base.auth.access import require_access
from workhour.costhour.service import (
    workday_costhour_team_summary_service,
    workday_costhour_department_aggregate_service,
    workday_costhour_task_status_detail_service,
    workday_costhour_member_summary_service,
    workday_costhour_team_project_detail_service,
    workday_costhour_project_name_detail_service,
)
from workhour.costhour.attendance import (
    get_attendance_service,
    save_attendance_service,
)


def register(bp, ok, fail):
    def require_workday_access():
        return require_access(fail, any_permissions=("page.workday_costhour",))

    @bp.route("/stats/workday_costhour/team_summary", methods=["POST"])
    def stats_workday_costhour_team_summary():
        _, denied = require_workday_access()
        if denied:
            return denied
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
        _, denied = require_workday_access()
        if denied:
            return denied
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
        _, denied = require_workday_access()
        if denied:
            return denied
        try:
            payload = request.get_json(silent=True) or {}
            result = workday_costhour_task_status_detail_service(payload)
            if result.get("success"):
                return ok(result.get("data") or {})
            return fail(result.get("error", "task status detail aggregate failed"), code=400, data=result.get("data"))
        except Exception as e:
            return fail(str(e), code=500, data={})

    @bp.route("/stats/workday_costhour/member_summary", methods=["POST"])
    def stats_workday_costhour_member_summary():
        _, denied = require_workday_access()
        if denied:
            return denied
        try:
            payload = request.get_json(silent=True) or {}
            result = workday_costhour_member_summary_service(payload)
            if result.get("success"):
                return ok(result.get("data") or {})
            return fail(result.get("error", "member summary aggregate failed"), code=400, data=result.get("data"))
        except Exception as e:
            return fail(str(e), code=500, data={})

    @bp.route("/stats/workday_costhour/team_project_detail", methods=["POST"])
    def stats_workday_costhour_team_project_detail():
        _, denied = require_workday_access()
        if denied:
            return denied
        try:
            payload = request.get_json(silent=True) or {}
            result = workday_costhour_team_project_detail_service(payload)
            if result.get("success"):
                return ok(result.get("data") or {})
            return fail(result.get("error", "team project detail failed"), code=400, data=result.get("data"))
        except Exception as e:
            return fail(str(e), code=500, data={})

    @bp.route("/stats/workday_costhour/project_name_detail", methods=["POST"])
    def stats_workday_costhour_project_name_detail():
        _, denied = require_workday_access()
        if denied:
            return denied
        try:
            payload = request.get_json(silent=True) or {}
            result = workday_costhour_project_name_detail_service(payload)
            if result.get("success"):
                return ok(result.get("data") or {})
            return fail(result.get("error", "project name detail aggregate failed"), code=400, data=result.get("data"))
        except Exception as e:
            return fail(str(e), code=500, data={})

    # ── 员工出勤表 读取 ──

    @bp.route("/stats/attendance/get", methods=["POST"])
    def stats_attendance_get():
        _, denied = require_workday_access()
        if denied:
            return denied
        try:
            payload = request.get_json(silent=True) or {}
            result = get_attendance_service(payload)
            if result.get("success"):
                return ok(result.get("data") or {})
            return fail(result.get("error", "failed to fetch attendance records"), code=400, data=result.get("data"))
        except Exception as e:
            return fail(str(e), code=500, data={})

    # ── 员工出勤表 保存/更新 ──

    @bp.route("/stats/attendance/save", methods=["POST"])
    def stats_attendance_save():
        _, denied = require_workday_access()
        if denied:
            return denied
        try:
            payload = request.get_json(silent=True) or {}
            result = save_attendance_service(payload)
            if result.get("success"):
                return ok(result.get("data") or {})
            return fail(result.get("error", "failed to save attendance records"), code=400, data=result.get("data"))
        except Exception as e:
            return fail(str(e), code=500, data={})
