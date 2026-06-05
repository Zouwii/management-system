from typing import Any, Dict

from base.dingtalk_client import fetch_dingtalk_json


def health_service() -> Dict[str, Any]:
    """健康检查业务。"""
    return {"success": True, "message": "ok"}


def dingtalk_proxy_service(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    钉钉代理业务：
    - 接收前端 payload
    - 调用钉钉客户端
    - 返回统一结构给路由层
    """
    dingtalk_data = fetch_dingtalk_json(payload or {})
    ok = bool(dingtalk_data.get("ok", True))
    return {
        "success": ok,
        "data": dingtalk_data,
        "meta": {"endpoint": "/api/bt/proxy"},
    }


def dingtalk_gettoken_service(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    获取 token 业务：
    - 优先用 payload 的 appKey/appSecret
    - 未传则读 config.json
    - 自动走缓存有效期判断
    """
    dingtalk_data = fetch_dingtalk_json(payload or {})
    ok = bool(dingtalk_data.get("ok", True))
    return {
        "success": ok,
        "data": dingtalk_data,
        "meta": {"endpoint": "/api/bt/gettoken"},
    }

