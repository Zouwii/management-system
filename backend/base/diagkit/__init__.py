"""DiagKit 诊断终端辅助路由（v4 简化版）。

v4 的 auth-proxy 已改用 Flask session 透传方案，通过标准 auth 端点完成认证：
  POST /auth/get_token  → authCode 换 session
  GET  /auth/me         → 校验 session
  POST /auth/logout     → 清除 session

本模块仅保留 /diagkit/config 端点供诊断终端查询 OAuth 配置。
旧的 SID 机制（/diagkit/callback、/diagkit/status）已移除。
"""
