"""DiagKit 诊断终端辅助路由（v4 简化版）。

v4 的 auth-proxy 已改用 Flask session 透传方案，通过标准 auth 端点完成认证：
  POST /auth/get_token  → authCode 换 session
  GET  /auth/me         → 校验 session
  POST /auth/logout     → 清除 session

本模块仅保留 /diagkit/config 端点供诊断终端查询 OAuth 配置。
旧的 SID 机制（/diagkit/callback、/diagkit/status）已移除。
"""

from flask import request
from base.dingtalk_client import build_dingtalk_oauth_url


def register(bp, ok, fail):
    @bp.route("/diagkit/config", methods=["GET"])
    def diagkit_config():
        """返回 OAuth URL 模板（redirect_uri 由 auth-proxy 自行替换）。"""
        # 使用一个占位 redirect_uri，auth-proxy 会替换为实际的 callback 地址
        host = request.host_url.rstrip("/")
        redirect_uri = f"{host}/api/bt/diagkit/callback"
        out = build_dingtalk_oauth_url(redirect_uri=redirect_uri)
        if not out.get("ok"):
            return fail(out.get("error", "failed to build oauth url"), code=500)
        return ok({"oauth_url": out.get("url", "")})
