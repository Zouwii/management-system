import json
import os
from pathlib import Path
import time
from typing import Dict, Any

import requests


def _sanitize_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """避免在返回里把密钥原文回显（例如 clientSecret/appSecret）。"""
    redacted = dict(payload or {})
    for k in list(redacted.keys()):
        lk = str(k).lower()
        if "secret" in lk:
            redacted[k] = "***"
    return redacted


def _load_config_json() -> Dict[str, Any]:
    """
    从同目录 `config.json` 读取配置。
    期望字段：appkey / appsecret
    """
    # 容器化部署时优先从环境变量读取密钥，避免把敏感信息打进镜像。
    env_appkey = os.getenv("DINGTALK_APPKEY") or ""
    env_appsecret = os.getenv("DINGTALK_APPSECRET") or ""
    if env_appkey and env_appsecret:
        # 这里不提供 access_token/token_expire_at，让上层逻辑走 gettoken 刷新；缓存写回会被 _save_config_json 安全吞掉。
        return {
            "appkey": env_appkey,
            "appsecret": env_appsecret,
            "access_token": "",
            "token_expire_at": 0,
        }

    cfg_path = Path(__file__).with_name("config.json")
    try:
        raw = cfg_path.read_text(encoding="utf-8")
        data = json.loads(raw) if raw.strip() else {}
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception:
        # 配置文件损坏/格式不对时，返回空让上层给出缺参错误
        return {}


def _save_config_json(cfg: Dict[str, Any]) -> None:
    """把配置写回同目录 `config.json`。"""
    cfg_path = Path(__file__).with_name("config.json")
    try:
        cfg_path.write_text(
            json.dumps(cfg, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except Exception:
        # 容器镜像/只读挂载场景下，不强制写回缓存 token。
        return


def _get_cached_token_if_valid(cfg: Dict[str, Any], now_ts: int) -> str:
    """
    读取缓存 token：
    - 要求存在 access_token 和 token_expire_at
    - 提前 60 秒视作过期，避免临界时间请求失败
    """
    token = cfg.get("access_token")
    expire_at = cfg.get("token_expire_at")
    if not token or not expire_at:
        return ""
    try:
        if int(expire_at) > now_ts + 60:
            return str(token)
    except Exception:
        return ""
    return ""


def fetch_dingtalk_json(payload: Dict) -> Dict:
    """
    钉钉 token 获取（按你给的 curl 形式）：

    - GET https://oapi.dingtalk.com/gettoken?appkey=...&appsecret=...

    payload 字段（兼容多种写法）：
    - appKey/appSecret（或 appkey/appsecret）
    如果 payload 未提供，则回退读取 `backend/config.json` 里的配置。
    """
    payload = payload or {}
    cfg = _load_config_json()
    now_ts = int(time.time())
    app_key = (
        payload.get("appKey")
        or payload.get("appkey")
        or payload.get("app_key")
        or cfg.get("appkey")
        or cfg.get("appKey")
        or cfg.get("app_key")
    )
    app_secret = (
        payload.get("appSecret")
        or payload.get("appsecret")
        or payload.get("app_secret")
        or cfg.get("appsecret")
        or cfg.get("appSecret")
        or cfg.get("app_secret")
    )
    force_refresh = bool(payload.get("force_refresh"))

    if not app_key or not app_secret:
        return {
            "source": "dingtalk_oapi_gettoken",
            "ok": False,
            "error": "missing appKey/appSecret (or set appkey/appsecret in backend/config.json)",
            "received": _sanitize_payload(payload),
            "timestamp": now_ts,
        }

    # 主流程优先使用本地缓存 token，失效时再调用 gettoken
    if not force_refresh:
        cached_token = _get_cached_token_if_valid(cfg, now_ts)
        if cached_token:
            return {
                "source": "dingtalk_oapi_gettoken_cache",
                "ok": True,
                "dingtalk": {
                    "access_token": cached_token,
                    "errcode": 0,
                    "errmsg": "ok(cached)",
                    "expires_in": max(int(cfg.get("token_expire_at", now_ts)) - now_ts, 0),
                },
                "timestamp": now_ts,
            }

    url = "https://oapi.dingtalk.com/gettoken"
    params = {"appkey": app_key, "appsecret": app_secret}
    try:
        resp = requests.get(url, params=params, timeout=30)
        data = resp.json()
        ok = data.get("errcode", 0) == 0
        errcode = data.get("errcode")
        errmsg = data.get("errmsg")
        if ok and data.get("access_token"):
            expires_in = int(data.get("expires_in", 7200))
            cfg["appkey"] = app_key
            cfg["appsecret"] = app_secret
            cfg["access_token"] = data.get("access_token")
            cfg["token_expires_in"] = expires_in
            cfg["token_expire_at"] = now_ts + expires_in
            _save_config_json(cfg)
        return {
            "source": "dingtalk_oapi_gettoken",
            "ok": ok,
            "dingtalk": data,
            "error": "" if ok else "dingtalk gettoken failed: errcode={}, errmsg={}".format(errcode, errmsg),
            "timestamp": now_ts,
        }
    except Exception as e:
        return {
            "source": "dingtalk_oapi_gettoken",
            "ok": False,
            "error": str(e),
            "timestamp": now_ts,
        }


def get_valid_access_token(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    获取有效 access_token：
    - 先走本地缓存校验
    - 缓存失效时自动请求钉钉 gettoken
    """
    token_result = fetch_dingtalk_json(payload or {})
    if not token_result.get("ok"):
        return {
            "ok": False,
            "error": token_result.get("error", "failed to fetch dingtalk token"),
            "source": token_result.get("source", "dingtalk_oapi_gettoken"),
            "timestamp": int(time.time()),
        }

    dingtalk_data = token_result.get("dingtalk") or {}
    access_token = dingtalk_data.get("access_token")
    if not access_token:
        return {
            "ok": False,
            "error": "missing access_token in dingtalk response",
            "source": token_result.get("source", "dingtalk_oapi_gettoken"),
            "timestamp": int(time.time()),
        }

    return {
        "ok": True,
        "access_token": access_token,
        "source": token_result.get("source", "dingtalk_oapi_gettoken"),
        "timestamp": int(time.time()),
    }


def get_config_userids() -> Dict[str, str]:
    """读取 config.json 里的 userids 配置。"""
    ids_path = Path(__file__).with_name("ids.json")
    try:
        raw = ids_path.read_text(encoding="utf-8")
        data = json.loads(raw) if raw.strip() else {}
        userids = (data or {}).get("userids")
        return userids if isinstance(userids, dict) else {}
    except Exception:
        # fallback：兼容旧逻辑（可能存在 config.json）
        cfg = _load_config_json()
        userids = cfg.get("userids")
        return userids if isinstance(userids, dict) else {}


def get_config_projectids() -> Dict[str, str]:
    """读取 config.json 里的 projectids 配置。"""
    ids_path = Path(__file__).with_name("ids.json")
    try:
        raw = ids_path.read_text(encoding="utf-8")
        data = json.loads(raw) if raw.strip() else {}
        projectids = (data or {}).get("projectids")
        return projectids if isinstance(projectids, dict) else {}
    except Exception:
        # fallback：兼容旧逻辑（可能存在 config.json）
        cfg = _load_config_json()
        projectids = cfg.get("projectids")
        return projectids if isinstance(projectids, dict) else {}


# 兼容你提到的 “ftech” 名字（如果外部代码就是这么调用的）
def ftech(payload: Dict) -> Dict:
    return fetch_dingtalk_json(payload)

