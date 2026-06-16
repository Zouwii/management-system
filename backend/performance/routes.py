"""绩效：成员规则 fill / calculate / query / import"""

from flask import request

from performance.service import (
    fill_member_input_service,
    calculate_member_quarter_performance_service,
    query_quarter_performance_service,
    list_team_import_users_service,
    batch_import_service,
    update_member_performance_service,
    list_teams_service,
    list_members_service,
)


def register(bp, ok, fail):
    @bp.route("/perf/fill-quarter-member", methods=["POST"])
    def perf_fill_quarter_member():
        try:
            payload = request.get_json(silent=True) or {}
            out = fill_member_input_service(payload)
            if out.get("success"):
                return ok(out.get("data") or {})
            return fail(out.get("error", "fill failed"), code=400, data=out.get("data") or {})
        except Exception as e:
            return fail(str(e), code=500, data={})

    @bp.route("/perf/calculate-quarter-member", methods=["POST"])
    def perf_calculate_quarter_member():
        try:
            payload = request.get_json(silent=True) or {}
            out = calculate_member_quarter_performance_service(payload)
            if out.get("success"):
                return ok(out.get("data") or {})
            return fail(out.get("error", "calculate failed"), code=400, data=out.get("data") or {})
        except Exception as e:
            return fail(str(e), code=500, data={})

    @bp.route("/perf/query", methods=["GET"])
    def perf_query():
        try:
            payload = {
                "year": request.args.get("year"),
                "quarter": request.args.get("quarter"),
                "user_id": request.args.get("userId", request.args.get("user_id", "")),
            }
            out = query_quarter_performance_service(payload)
            if out.get("success"):
                return ok(out.get("data") or {})
            return fail(out.get("error", "query failed"), code=400, data=out.get("data") or {})
        except Exception as e:
            return fail(str(e), code=500, data={})

    @bp.route("/perf/team-import-users", methods=["GET"])
    def perf_team_import_users():
        try:
            payload = {
                "year": request.args.get("year"),
                "quarter": request.args.get("quarter"),
                "team": request.args.get("team"),
            }
            out = list_team_import_users_service(payload)
            if out.get("success"):
                return ok(out.get("data") or {})
            return fail(out.get("error", "list failed"), code=400, data=out.get("data") or {})
        except Exception as e:
            return fail(str(e), code=500, data={})

    @bp.route("/perf/batch-import", methods=["POST"])
    def perf_batch_import():
        try:
            payload = request.get_json(silent=True) or {}
            out = batch_import_service(payload)
            if out.get("success"):
                return ok(out.get("data") or {})
            return fail(out.get("error", "import failed"), code=400, data=out.get("data") or {})
        except Exception as e:
            return fail(str(e), code=500, data={})

    @bp.route("/perf/update-quarter-member", methods=["POST"])
    def perf_update_quarter_member():
        try:
            payload = request.get_json(silent=True) or {}
            out = update_member_performance_service(payload)
            if out.get("success"):
                return ok(out.get("data") or {})
            return fail(out.get("error", "update failed"), code=400, data=out.get("data") or {})
        except Exception as e:
            return fail(str(e), code=500, data={})

    @bp.route("/perf/teams", methods=["GET"])
    def perf_teams():
        try:
            out = list_teams_service()
            if out.get("success"):
                return ok(out.get("data") or {})
            return fail(out.get("error", "list teams failed"), code=400, data=out.get("data") or {})
        except Exception as e:
            return fail(str(e), code=500, data={})

    @bp.route("/perf/members", methods=["GET"])
    def perf_members():
        try:
            payload = {"team": request.args.get("team", "")}
            out = list_members_service(payload)
            if out.get("success"):
                return ok(out.get("data") or {})
            return fail(out.get("error", "list members failed"), code=400, data=out.get("data") or {})
        except Exception as e:
            return fail(str(e), code=500, data={})
