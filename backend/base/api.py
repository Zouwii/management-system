"""
HTTP API 入口（类似 Go 里集中 init 注册路由）。

- Blueprint、统一响应：本文件
- 按业务分组的具体路由：route_registry/ 下各模块的 register(bp, ok, fail)
- 一览与注册顺序：route_registry/__init__.py
"""

from flask import Blueprint, jsonify

from base.route_registry import register_all_routes
from base.route_registry.route_index import get_all_route_index

api_bp = Blueprint("api_bt", __name__, url_prefix="/api/bt")


def _ok(data):
    return jsonify({"code": 200, "error": "", "data": data}), 200


def _fail(msg, code=400, data=None):
    return jsonify({"code": code, "error": msg, "data": data if data is not None else {}}), code


@api_bp.route("/routes", methods=["GET"])
def api_routes_index():
    return _ok(get_all_route_index())


@api_bp.route("/monitor/api-stats", methods=["GET"])
def api_monitor_stats():
    """Return real-time DingTalk API call statistics."""
    try:
        from base.api_monitor import monitor
        return _ok(monitor.snapshot())
    except Exception as e:
        return _fail(str(e), code=500)


register_all_routes(api_bp, _ok, _fail)
