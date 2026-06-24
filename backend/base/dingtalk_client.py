import json
import os
from pathlib import Path
import time
from typing import Dict, Any, Optional

import requests


def _record(endpoint: str, status: int, latency_ms: int, error: str = "", source: str = "auth"):
    """统一入口：记录钉钉 API 调用到 api_call_logs 表"""
    try:
        from base.api_monitor import record_api_call
        record_api_call(endpoint, status, latency_ms, error, source)
    except Exception:
        pass


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
    cfg_path = Path(__file__).with_name("config.json")
    try:
        raw = cfg_path.read_text(encoding="utf-8")
        data = json.loads(raw) if raw.strip() else {}
        if isinstance(data, dict):
            return data
        return {}
    except FileNotFoundError:
        # config.json 不存在时回退环境变量
        env_appkey = os.getenv("DINGTALK_APPKEY") or ""
        env_appsecret = os.getenv("DINGTALK_APPSECRET") or ""
        if env_appkey and env_appsecret:
            return {
                "appkey": env_appkey,
                "appsecret": env_appsecret,
                "access_token": "",
                "token_expire_at": 0,
            }
        return {}
    except Exception:
        # 配置文件损坏/格式不对时，返回空让上层给出缺参错误
        return {}


def _get_dingtalk_app_credentials(payload: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    payload = payload or {}
    cfg = _load_config_json()
    app_key = (
        payload.get("clientId")
        or payload.get("client_id")
        or payload.get("appKey")
        or payload.get("appkey")
        or payload.get("app_key")
        or cfg.get("appkey")
        or cfg.get("appKey")
        or cfg.get("app_key")
        or os.getenv("DINGTALK_APPKEY")
        or ""
    )
    app_secret = (
        payload.get("appSecret")
        or payload.get("appsecret")
        or payload.get("app_secret")
        or cfg.get("appsecret")
        or cfg.get("appSecret")
        or cfg.get("app_secret")
        or os.getenv("DINGTALK_APPSECRET")
        or ""
    )
    return {
        "app_key": str(app_key).strip(),
        "app_secret": str(app_secret).strip(),
    }


def build_dingtalk_oauth_url(redirect_uri: str, state: str = "") -> Dict[str, Any]:
    creds = _get_dingtalk_app_credentials()
    if not creds["app_key"] or not creds["app_secret"]:
        return {
            "ok": False,
            "error": "missing appKey/appSecret (or set DINGTALK_APPKEY/DINGTALK_APPSECRET)",
        }
    params = {
        "client_id": creds["app_key"],
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid corpid",
        "prompt": "consent",
    }
    if state:
        params["state"] = state
    query = requests.compat.urlencode(params)
    return {
        "ok": True,
        "url": f"https://login.dingtalk.com/oauth2/auth?{query}",
    }


def get_dingtalk_login_client_config(payload: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    payload = payload or {}
    cfg = _load_config_json()
    creds = _get_dingtalk_app_credentials(payload)
    corp_id = (
        payload.get("corpId")
        or payload.get("corp_id")
        or cfg.get("corpId")
        or cfg.get("corp_id")
        or os.getenv("DINGTALK_CORP_ID")
        or ""
    )
    return {
        "corpId": str(corp_id).strip(),
        "clientId": creds.get("app_key", ""),
    }


def exchange_dingtalk_auth_code(auth_code: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    auth_code = str(auth_code or "").strip()
    if not auth_code:
        return {"ok": False, "error": "missing authCode"}

    creds = _get_dingtalk_app_credentials(payload)
    if not creds["app_key"] or not creds["app_secret"]:
        return {
            "ok": False,
            "error": "missing appKey/appSecret (or set DINGTALK_APPKEY/DINGTALK_APPSECRET)",
        }

    try:
        t0 = time.time()
        resp = requests.post(
            "https://api.dingtalk.com/v1.0/oauth2/userAccessToken",
            headers={"Content-Type": "application/json"},
            json={
                "clientId": creds["app_key"],
                "clientSecret": creds["app_secret"],
                "code": auth_code,
                "grantType": "authorization_code",
            },
            timeout=30,
        )
        _record("/v1.0/oauth2/userAccessToken", resp.status_code, int((time.time() - t0) * 1000))
        data = resp.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}

    access_token = (data or {}).get("accessToken")
    if not access_token:
        return {"ok": False, "error": f"failed to get user access token: {data}"}

    return {"ok": True, "data": data}


def get_dingtalk_user_info(access_token: str) -> Dict[str, Any]:
    token = str(access_token or "").strip()
    if not token:
        return {"ok": False, "error": "missing accessToken"}

    try:
        t0 = time.time()
        resp = requests.get(
            "https://api.dingtalk.com/v1.0/contact/users/me",
            headers={"x-acs-dingtalk-access-token": token},
            timeout=30,
        )
        _record("/v1.0/contact/users/me", resp.status_code, int((time.time() - t0) * 1000))
        data = resp.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}

    # 钉钉常见字段：nick, unionId/openId
    if not (data or {}).get("nick"):
        return {"ok": False, "error": f"failed to get user info: {data}"}
    return {"ok": True, "data": data}


def get_userid_by_unionid(unionid: str) -> Dict[str, Any]:
    """
    用 unionId 换取钉钉 userid（企业内用户唯一 ID）。
    依赖企业 access_token（应用级 token）。
    """
    uid = str(unionid or "").strip()
    if not uid:
        return {"ok": False, "error": "missing unionid"}

    token_out = get_valid_access_token({})
    if not token_out.get("ok"):
        return {"ok": False, "error": token_out.get("error", "failed to get corp access_token")}

    access_token = token_out.get("access_token")
    try:
        t0 = time.time()
        resp = requests.get(
            "https://oapi.dingtalk.com/user/getUseridByUnionid",
            params={"access_token": access_token, "unionid": uid},
            timeout=30,
        )
        _record("/user/getUseridByUnionid", resp.status_code, int((time.time() - t0) * 1000))
        data = resp.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}

    # oapi 返回：{"errcode":0,"errmsg":"ok","userid":"xxx"}
    if int(data.get("errcode", -1)) != 0 or not data.get("userid"):
        return {"ok": False, "error": f"getUseridByUnionid failed: {data}"}
    return {"ok": True, "data": data}

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
        t0 = time.time()
        resp = requests.get(url, params=params, timeout=30)
        _record("/gettoken", resp.status_code, int((time.time() - t0) * 1000))
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


def _normalize_userids(raw_userids: Any) -> Dict[str, str]:
    """
    兼容两种写法：
    1) "张三": "012345"
    2) "张三": {"userId": "012345", "character": 1}
    """
    out: Dict[str, str] = {}
    if not isinstance(raw_userids, dict):
        return out
    for name, v in raw_userids.items():
        nm = str(name)
        if isinstance(v, dict):
            uid = v.get("userId", v.get("user_id", v.get("id", "")))
        else:
            uid = v
        uid_s = str(uid or "").strip()
        if uid_s:
            out[nm] = uid_s
    return out


def get_config_user_characters() -> Dict[str, int]:
    """
    从 ids.json/config.json 读取用户默认 character（按中文名索引）。
    仅在 value 为对象且包含 character 字段时返回。
    """
    ids_path = Path(__file__).with_name("ids.json")
    try:
        raw = ids_path.read_text(encoding="utf-8")
        data = json.loads(raw) if raw.strip() else {}
        userids = (data or {}).get("userids")
    except Exception:
        cfg = _load_config_json()
        userids = cfg.get("userids")

    out: Dict[str, int] = {}
    if not isinstance(userids, dict):
        return out
    for name, v in userids.items():
        if not isinstance(v, dict):
            continue
        ch = v.get("character")
        try:
            out[str(name)] = int(ch)
        except Exception:
            continue
    return out


def get_config_userids() -> Dict[str, str]:
    """读取 config.json 里的 userids 配置。"""
    ids_path = Path(__file__).with_name("ids.json")
    try:
        raw = ids_path.read_text(encoding="utf-8")
        data = json.loads(raw) if raw.strip() else {}
        userids = (data or {}).get("userids")
        return _normalize_userids(userids)
    except Exception:
        # fallback：兼容旧逻辑（可能存在 config.json）
        cfg = _load_config_json()
        userids = cfg.get("userids")
        return _normalize_userids(userids)


def get_config_user_meta() -> Dict[str, Dict[str, Any]]:
    """
    读取 ids.json 里的 userids 扩展信息（按中文名索引）。

    期望格式（示例）：
    {
      "userids": {
        "张三": { "userId": "...", "character": 1, "team_id": 0, "is_nav_lead": false, "is_servo_lead": false },
        "李四": "012345"  # 旧格式也兼容
      }
    }

    返回：
    { "张三": { "userId": "...", "character": 1, "team_id": 0, "is_nav_lead": False, "is_servo_lead": False }, ... }
    """
    ids_path = Path(__file__).with_name("ids.json")
    try:
        raw = ids_path.read_text(encoding="utf-8")
        data = json.loads(raw) if raw.strip() else {}
        userids = (data or {}).get("userids")
    except Exception:
        # fallback：兼容旧逻辑（可能存在 config.json）
        cfg = _load_config_json()
        userids = cfg.get("userids")

    out: Dict[str, Dict[str, Any]] = {}
    if not isinstance(userids, dict):
        return out

    for name, v in userids.items():
        nm = str(name)
        if isinstance(v, dict):
            uid = v.get("userId", v.get("user_id", v.get("id", "")))
            try:
                character = int(v.get("character", 0) or 0)
            except Exception:
                character = 0
            team_id = v.get("team_id", v.get("teamId", v.get("team_id".upper(), None)))
            # 允许 ids.json 里用 true/false 或 0/1
            is_nav_lead = bool(v.get("is_nav_lead", v.get("isNavLead", False)))
            is_servo_lead = bool(v.get("is_servo_lead", v.get("isServoLead", False)))
        else:
            uid = v
            character = 0
            team_id = None
            is_nav_lead = False
            is_servo_lead = False

        uid_s = str(uid or "").strip()
        if not uid_s:
            continue

        out[nm] = {
            "userId": uid_s,
            "character": character,
            "team_id": team_id,
            "is_nav_lead": is_nav_lead,
            "is_servo_lead": is_servo_lead,
        }

    return out


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

