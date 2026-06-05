"""健康检查、钉钉代理、gettoken"""

from flask import request

from base.health.proxy import (
    dingtalk_gettoken_service,
    dingtalk_proxy_service,
    health_service,
)


def register(bp, ok, fail):
    @bp.route("/health", methods=["GET"])
    def health():
        try:
            return ok(health_service())
        except Exception as e:
            return fail(str(e), code=500, data={})

    @bp.route("/proxy", methods=["POST"])
    def proxy_dingtalk():
        try:
            payload = request.get_json(silent=True) or {}
            result = dingtalk_proxy_service(payload)
            if result.get("success"):
                return ok(result)
            return fail(result.get("error", "proxy failed"), code=400, data=result)
        except Exception as e:
            return fail(str(e), code=500, data={})

    @bp.route("/gettoken", methods=["GET", "POST"])
    def gettoken():
        try:
            payload = request.get_json(silent=True) or {}
            result = dingtalk_gettoken_service(payload)
            if result.get("success"):
                return ok(result)
            return fail(result.get("error", "gettoken failed"), code=400, data=result)
        except Exception as e:
            return fail(str(e), code=500, data={})
