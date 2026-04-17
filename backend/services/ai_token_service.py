import json
import time
from pathlib import Path
from typing import Any, Dict

import requests

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"
_DEFAULT_TOKEN_API = "http://claude-test.server22.jz/api/v1/token"


def _load_config() -> Dict[str, Any]:
    try:
        raw = _CONFIG_PATH.read_text(encoding="utf-8")
        data = json.loads(raw) if raw.strip() else {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_config(cfg: Dict[str, Any]) -> None:
    _CONFIG_PATH.write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _mask_token(token: str) -> str:
    s = str(token or "").strip()
    if len(s) <= 10:
        return "*" * len(s)
    return f"{s[:6]}...{s[-4:]}"


def get_ai_token_status_service() -> Dict[str, Any]:
    cfg = _load_config()
    now_ts = int(time.time())
    expire_at = int(cfg.get("ai_token_expire_at", 0) or 0)
    remaining = max(expire_at - now_ts, 0) if expire_at > 0 else 0
    token = str(cfg.get("ai_access_token", "") or "")
    return {
        "success": True,
        "ai_token_api": str(cfg.get("ai_token_api") or _DEFAULT_TOKEN_API),
        "ai_api_key_set": bool(str(cfg.get("ai_api_key", "") or "").strip()),
        "ai_access_token_set": bool(token),
        "ai_access_token_masked": _mask_token(token),
        "ai_token_expires_in": int(cfg.get("ai_token_expires_in", 0) or 0),
        "ai_token_expire_at": expire_at,
        "ai_token_remaining_seconds": remaining,
        "ai_token_refresh_seconds": int(cfg.get("ai_token_refresh_seconds", 3600) or 3600),
    }


def refresh_ai_token_service() -> Dict[str, Any]:
    cfg = _load_config()
    token_api = str(cfg.get("ai_token_api") or _DEFAULT_TOKEN_API).strip()
    api_key = str(cfg.get("ai_api_key", "") or "").strip()
    if not token_api:
        return {"success": False, "error": "missing ai_token_api"}
    if not api_key:
        return {"success": False, "error": "missing ai_api_key"}

    now_ts = int(time.time())
    try:
        resp = requests.post(
            token_api,
            headers={"Content-Type": "application/json"},
            json={"api_key": api_key},
            timeout=30,
        )
        data = resp.json()
    except Exception as e:
        return {"success": False, "error": str(e)}

    token = str((data or {}).get("token") or (data or {}).get("access_token") or "").strip()
    if not token:
        return {"success": False, "error": f"token 接口未返回 token 字段: {data}"}

    expires_in = int((data or {}).get("expires_in", 3600) or 3600)
    expire_at = now_ts + expires_in
    cfg["ai_access_token"] = token
    cfg["ai_authorization"] = f"Bearer {token}"
    cfg["ai_token_expires_in"] = expires_in
    cfg["ai_token_expire_at"] = expire_at
    cfg["ai_token_last_refresh_at"] = now_ts
    _save_config(cfg)

    return {
        "success": True,
        "ai_access_token_masked": _mask_token(token),
        "ai_token_expires_in": expires_in,
        "ai_token_expire_at": expire_at,
    }


def get_valid_ai_token_service() -> Dict[str, Any]:
    cfg = _load_config()
    now_ts = int(time.time())
    token = str(cfg.get("ai_access_token", "") or "").strip()
    expire_at = int(cfg.get("ai_token_expire_at", 0) or 0)
    if token and expire_at > now_ts + 60:
        return {
            "success": True,
            "token": token,
            "authorization": f"Bearer {token}",
            "from_cache": True,
            "expires_in": expire_at - now_ts,
        }

    out = refresh_ai_token_service()
    if not out.get("success"):
        return out
    cfg = _load_config()
    token = str(cfg.get("ai_access_token", "") or "").strip()
    if not token:
        return {"success": False, "error": "refresh succeeded but token missing in config"}
    expire_at = int(cfg.get("ai_token_expire_at", 0) or 0)
    return {
        "success": True,
        "token": token,
        "authorization": f"Bearer {token}",
        "from_cache": False,
        "expires_in": max(expire_at - now_ts, 0),
    }


def get_ai_authorization_header_service() -> Dict[str, Any]:
    out = get_valid_ai_token_service()
    if not out.get("success"):
        return out
    return {
        "success": True,
        "authorization": out.get("authorization", ""),
        "from_cache": out.get("from_cache", True),
        "expires_in": int(out.get("expires_in", 0) or 0),
    }
