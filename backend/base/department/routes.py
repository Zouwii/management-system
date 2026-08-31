"""部门总览路由 — 挂载在 api_bp，路径 /bt/dashboard/department-overview。"""

from base.department.service import department_overview_service
from base.auth.access import require_access
from flask import request


def register(bp, ok, fail):
    @bp.route("/dashboard/department-overview", methods=["GET"])
    def bt_dashboard_department_overview():
        _, denied = require_access(fail, any_permissions=("page.department_overview",))
        if denied:
            return denied
        try:
            out = department_overview_service(
                start_date=request.args.get("startDate") or request.args.get("start_time"),
                end_date=request.args.get("endDate") or request.args.get("end_time"),
            )
            if out.get("success"):
                return ok(out.get("data") or {})
            return fail(out.get("error", "query failed"), code=400, data=out.get("data") or {})
        except Exception as e:
            return fail(str(e), code=500, data={})
