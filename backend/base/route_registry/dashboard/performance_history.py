"""绩效历史查询 — 挂载在 dashboard_bp 上，路径 /dashboard/performance-history。"""

from flask import request

from base.route_registry.dashboard import dashboard_bp, _ok, _fail
from performance.service import performance_history_service


@dashboard_bp.route("/performance-history", methods=["GET"])
def performance_history():
    try:
        payload = {"target": request.args.get("target", "")}
        out = performance_history_service(payload)
        if out.get("success"):
            return _ok(out.get("data") or {})
        return _fail(out.get("error", "query failed"), code=400, data=out.get("data") or {})
    except Exception as e:
        return _fail(str(e), code=500, data={})
