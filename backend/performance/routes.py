"""绩效：成员规则 fill / calculate"""

from flask import request

from performance.service import (
    fill_member_input_service,
    calculate_member_quarter_performance_service,
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
