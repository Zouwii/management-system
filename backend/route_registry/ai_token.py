"""AI token 管理接口：查看状态、手动刷新、获取 Authorization 头。"""

from services.ai_token_service import (
    get_ai_authorization_header_service,
    get_ai_token_status_service,
    refresh_ai_token_service,
)


def register(bp, ok, fail):
    @bp.route("/ai/token/status", methods=["GET"])
    def ai_token_status():
        try:
            return ok(get_ai_token_status_service())
        except Exception as e:
            return fail(str(e), code=500, data={})

    @bp.route("/ai/token/refresh", methods=["POST"])
    def ai_token_refresh():
        try:
            out = refresh_ai_token_service()
            if out.get("success"):
                return ok(out)
            return fail(out.get("error", "refresh ai token failed"), code=400, data=out)
        except Exception as e:
            return fail(str(e), code=500, data={})

    @bp.route("/ai/token/authorization", methods=["GET"])
    def ai_token_authorization():
        try:
            out = get_ai_authorization_header_service()
            if out.get("success"):
                return ok(out)
            return fail(out.get("error", "get ai authorization failed"), code=400, data=out)
        except Exception as e:
            return fail(str(e), code=500, data={})
