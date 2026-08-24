"""应用组问题分析 API。"""

from flask import request

from application_team.report_service import (
    application_team_options_service,
    application_team_report_service,
)


def register(bp, ok, fail):
    @bp.route("/application-team/options", methods=["GET"])
    def application_team_options():
        try:
            result = application_team_options_service()
            return ok(result.get("data") or {}) if result.get("success") else fail(
                result.get("error", "application team options failed"), code=400, data=result.get("data") or {}
            )
        except Exception as exc:
            return fail(str(exc), code=500, data={})

    @bp.route("/application-team/report", methods=["POST"])
    def application_team_report():
        try:
            result = application_team_report_service(request.get_json(silent=True) or {})
            if result.get("success"):
                return ok(result.get("data") or {})
            return fail(result.get("error", "application team report failed"), code=400, data=result.get("data") or {})
        except Exception as exc:
            return fail(str(exc), code=500, data={})
