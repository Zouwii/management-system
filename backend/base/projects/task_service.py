from typing import Any, Dict
from datetime import datetime, timedelta, timezone
import copy
import json

import requests
import time

from base.dingtalk_client import get_valid_access_token


def _monitor_api(endpoint: str, status: int, latency_ms: int, error: str = "", source: str = ""):
    """Feed API call data to the in-memory + DB monitor."""
    try:
        from base.api_monitor import record_api_call
        record_api_call(endpoint, status, latency_ms, error, source)
    except Exception:
        pass

_RESULT_CACHE: Dict[str, Dict[str, Any]] = {}
_CACHE_TTL_PROJECT_QUERY_SEC = 45
_CACHE_TTL_TASK_QUERY_SEC = 60

# 软件开发 scenarioFieldConfigId：用于统计过滤
DEFAULT_SCENARIO_FIELD_CONFIG_ID = "647854bcd999c893061ef8b5"


def _make_cache_key(prefix: str, payload: Dict[str, Any], keys: list) -> str:
    selected = {k: payload.get(k) for k in keys}
    return "{}:{}".format(prefix, json.dumps(selected, ensure_ascii=False, sort_keys=True))


def _cache_get(key: str) -> Dict[str, Any]:
    item = _RESULT_CACHE.get(key)
    if not item:
        return {}
    if item.get("expire_at", 0) <= time.time():
        _RESULT_CACHE.pop(key, None)
        return {}
    return copy.deepcopy(item.get("value", {}))


def _cache_set(key: str, value: Dict[str, Any], ttl_sec: int) -> None:
    _RESULT_CACHE[key] = {
        "expire_at": time.time() + ttl_sec,
        "value": copy.deepcopy(value),
    }


def query_project_tasks_service(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    项目任务查询业务（钉钉）：
    GET /v1.0/project/users/{userId}/projectIds/{projectId}/tasks
    """
    payload = payload or {}
    user_id = payload.get("userId") or payload.get("userid")
    project_id = payload.get("projectId") or payload.get("projectid")
    if not user_id or not project_id:
        return {
            "success": False,
            "error": "missing userId or projectId",
            "meta": {"endpoint": "/api/bt/query_project_tasks"},
        }

    # 允许直接使用你传入的 token；未传时回退到本地缓存/自动刷新
    provided_token = payload.get("access_token") or payload.get("accessToken") or payload.get("token")
    token_source = "payload"
    if provided_token:
        access_token = provided_token
    else:
        token_result = get_valid_access_token(payload)
        if not token_result.get("ok"):
            return {
                "success": False,
                "error": token_result.get("error", "failed to get access token"),
                "data": token_result,
                "meta": {"endpoint": "/api/bt/query_project_tasks"},
            }
        access_token = token_result["access_token"]
        token_source = token_result.get("source", "dingtalk_oapi_gettoken")

    url = "https://api.dingtalk.com/v1.0/project/users/{}/projectIds/{}/tasks".format(
        user_id, project_id
    )
    params = {
        "maxResults": payload.get("maxResults", 500),
        "query": payload.get("query", ""),
    }

    force_refresh = bool(payload.get("force_refresh"))
    use_cache = (not provided_token) and (not force_refresh)
    max_pages = int(payload.get("maxPages", 20))
    if max_pages < 1:
        max_pages = 1

    cache_key = _make_cache_key(
        "project_tasks_query",
        {
            "userId": user_id,
            "projectId": project_id,
            "maxResults": params.get("maxResults"),
            "query": params.get("query"),
            "maxPages": max_pages,
        },
        ["userId", "projectId", "maxResults", "query", "maxPages"],
    )
    if use_cache:
        cached = _cache_get(cache_key)
        if cached:
            cached_meta = cached.get("meta") or {}
            cached_meta["cache_hit"] = True
            cached["meta"] = cached_meta
            return cached

    def _do_request(token: str, req_params: Dict[str, Any]):
        _start = time.time()
        resp = requests.get(
            url,
            params=req_params,
            headers={
                "x-acs-dingtalk-access-token": token,
                "Content-Type": "application/json",
            },
            timeout=30,
        )
        _monitor_api(
            endpoint="/v1.0/project/users/{userId}/projectIds/{projectId}/tasks",
            status=resp.status_code,
            latency_ms=int((time.time() - _start) * 1000),
            source="task_list",
        )
        return resp

    try:
        retries = int(payload.get("retries", 2))
        if retries < 0:
            retries = 0

        all_rows = []
        page_count = 0
        current_next_token = payload.get("nextToken")
        status_code = 500
        last_data: Dict[str, Any] = {}
        refresh_attempted = False
        refresh_ok = False
        refresh_error = ""

        while page_count < max_pages:
            req_params = {
                "maxResults": params.get("maxResults"),
                "query": params.get("query"),
            }
            if current_next_token:
                req_params["nextToken"] = current_next_token

            last_resp = None
            for attempt in range(retries + 1):
                resp = _do_request(access_token, req_params)
                last_resp = resp
                if resp.status_code != 503:
                    break
                if attempt < retries:
                    time.sleep(1.0 * (attempt + 1))

            try:
                data = last_resp.json() if last_resp is not None else {}
            except Exception:
                data = {"raw": last_resp.text if last_resp is not None else ""}
            status_code = last_resp.status_code if last_resp is not None else 500

            # token 失效时刷新并重试当前页一次（仅对非外部传入 token 生效）
            if (
                status_code == 400
                and isinstance(data, dict)
                and data.get("code") == "InvalidAuthentication"
                and not provided_token
            ):
                refresh_attempted = True
                refresh_payload = dict(payload)
                refresh_payload["force_refresh"] = True
                token_result = get_valid_access_token(refresh_payload)
                if token_result.get("ok"):
                    refresh_ok = True
                    access_token = token_result["access_token"]
                    token_source = token_result.get("source", "dingtalk_oapi_gettoken")
                    retry_resp = _do_request(access_token, req_params)
                    try:
                        data = retry_resp.json()
                    except Exception:
                        data = {"raw": retry_resp.text}
                    status_code = retry_resp.status_code
                else:
                    refresh_error = token_result.get("error", "force refresh token failed")

            if not (200 <= status_code < 300):
                last_data = data if isinstance(data, dict) else {}
                break

            rows = data.get("result") if isinstance(data, dict) else None
            if isinstance(rows, list):
                all_rows.extend(rows)
            last_data = data if isinstance(data, dict) else {}
            page_count += 1
            current_next_token = (data or {}).get("nextToken")
            if not current_next_token:
                break

        ok = 200 <= status_code < 300
        merged_dingtalk = dict(last_data) if isinstance(last_data, dict) else {}
        merged_dingtalk["result"] = all_rows
        result = {
            "success": ok,
            "data": {
                "status_code": status_code,
                "dingtalk": merged_dingtalk,
            },
            "meta": {
                "endpoint": "/api/bt/query_project_tasks",
                "token_source": token_source,
                "cache_hit": False,
                "page_count": page_count,
                "fetched_count": len(all_rows),
                "has_more": bool(current_next_token),
                "refresh_attempted": refresh_attempted,
                "refresh_ok": refresh_ok,
                "refresh_error": refresh_error,
            },
        }
        if result.get("success") and use_cache:
            _cache_set(cache_key, result, _CACHE_TTL_PROJECT_QUERY_SEC)
        return result
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "meta": {"endpoint": "/api/bt/query_project_tasks"},
        }


def query_user_tasks_service(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    任务查询业务（钉钉）：
    GET /v1.0/project/users/{userId}/tasks
    """
    payload = payload or {}
    user_id = payload.get("userId") or payload.get("userid")
    if not user_id:
        return {
            "success": False,
            "error": "missing userId",
            "meta": {"endpoint": "/api/bt/query_task_details"},
        }

    # 优先使用外部传入 token，未传则回退缓存/刷新
    provided_token = payload.get("access_token") or payload.get("accessToken") or payload.get("token")
    token_source = "payload"
    if provided_token:
        access_token = provided_token
    else:
        token_result = get_valid_access_token(payload)
        if not token_result.get("ok"):
            return {
                "success": False,
                "error": token_result.get("error", "failed to get access token"),
                "data": token_result,
                "meta": {"endpoint": "/api/bt/query_task_details"},
            }
        access_token = token_result["access_token"]
        token_source = token_result.get("source", "dingtalk_oapi_gettoken")

    url = "https://api.dingtalk.com/v1.0/project/users/{}/tasks".format(user_id)
    params = {}
    if payload.get("taskId"):
        params["taskId"] = payload.get("taskId")
    if payload.get("parentTaskId"):
        params["parentTaskId"] = payload.get("parentTaskId")

    force_refresh = bool(payload.get("force_refresh"))
    use_cache = (not provided_token) and (not force_refresh)
    cache_key = _make_cache_key(
        "user_tasks_query",
        {
            "userId": user_id,
            "taskId": params.get("taskId"),
            "parentTaskId": params.get("parentTaskId"),
        },
        ["userId", "taskId", "parentTaskId"],
    )
    if use_cache:
        cached = _cache_get(cache_key)
        if cached:
            cached_meta = cached.get("meta") or {}
            cached_meta["cache_hit"] = True
            cached["meta"] = cached_meta
            return cached

    headers = {
        "x-acs-dingtalk-access-token": access_token,
        "Content-Type": "application/json",
    }

    def _do_request(token: str):
        _start = time.time()
        resp = requests.get(
            url,
            params=params,
            headers={
                "x-acs-dingtalk-access-token": token,
                "Content-Type": "application/json",
            },
            timeout=30,
        )
        _monitor_api(
            endpoint="/v1.0/project/users/{userId}/tasks",
            status=resp.status_code,
            latency_ms=int((time.time() - _start) * 1000),
            source="task_detail",
        )
        return resp

    try:
        resp = _do_request(access_token)
        refresh_attempted = False
        refresh_ok = False
        refresh_error = ""
        try:
            data = resp.json()
        except Exception:
            data = {"raw": resp.text}
        status_code = resp.status_code

        # 缓存 token 偶发失效：自动强制刷新并重试一次（仅对非外部传入 token 生效）
        if (
            status_code == 400
            and isinstance(data, dict)
            and data.get("code") == "InvalidAuthentication"
            and not provided_token
        ):
            refresh_attempted = True
            refresh_payload = dict(payload)
            refresh_payload["force_refresh"] = True
            token_result = get_valid_access_token(refresh_payload)
            if token_result.get("ok"):
                refresh_ok = True
                access_token = token_result["access_token"]
                token_source = token_result.get("source", "dingtalk_oapi_gettoken")
                retry_resp = _do_request(access_token)
                try:
                    data = retry_resp.json()
                except Exception:
                    data = {"raw": retry_resp.text}
                status_code = retry_resp.status_code
            else:
                refresh_error = token_result.get("error", "force refresh token failed")

        ok = 200 <= status_code < 300
        result = {
            "success": ok,
            "data": {
                "status_code": status_code,
                "dingtalk": data,
            },
            "meta": {
                "endpoint": "/api/bt/query_task_details",
                "token_source": token_source,
                "cache_hit": False,
                "refresh_attempted": refresh_attempted,
                "refresh_ok": refresh_ok,
                "refresh_error": refresh_error,
            },
        }
        if ok and use_cache:
            _cache_set(cache_key, result, _CACHE_TTL_TASK_QUERY_SEC)
        return result
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "meta": {"endpoint": "/api/bt/query_task_details"},
        }


def _parse_iso_dt(value: Any) -> datetime:
    t = str(value or "").strip()
    if not t:
        raise ValueError("empty datetime value")
    if t.endswith("Z"):
        t = t[:-1] + "+00:00"
    dt = datetime.fromisoformat(t)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _subtract_one_year(dt: datetime) -> datetime:
    # 处理 2/29：若替换失败，则落到 2/28
    try:
        return dt.replace(year=dt.year - 1)
    except ValueError:
        # 通用兜底
        day = min(dt.day, 28)
        return dt.replace(year=dt.year - 1, day=day)


def _format_dt_for_tql(dt: datetime) -> str:
    # 参考前端 toISOString：包含毫秒 .000Z
    d = dt.astimezone(timezone.utc).replace(microsecond=0)
    # 强制补齐 .000Z
    return d.strftime("%Y-%m-%dT%H:%M:%S") + ".000Z"


def count_software_dev_tasks_in_config_last_year_service(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    统计：end_time 配置的一年前 到 end_time 区间内，
    软件开发 scenarioFieldConfigId == 默认值 的项目任务数量。

    输入：必须提供 userId / projectId（用于调用钉钉列表接口）
    """
    payload = payload or {}
    user_id = payload.get("userId") or payload.get("userid")
    project_id = payload.get("projectId") or payload.get("projectid")
    if not user_id or not project_id:
        return {
            "success": False,
            "error": "missing userId or projectId",
            "data": {},
        }

    max_results = int(payload.get("maxResults", 500) or 500)
    max_pages = int(payload.get("maxPages", 50) or 50)
    if max_pages < 1:
        max_pages = 1

    # 从数据库 config 表读取 end_time
    from base.db.engine import SessionLocal
    from base.db.orm import Config as DbConfig

    session = SessionLocal()
    try:
        end_row = (
            session.query(DbConfig)
            .filter(DbConfig.type_ == "end_time")
            .first()
        )
        if not end_row:
            return {
                "success": False,
                "error": "missing config end_time",
                "data": {},
            }
        end_dt = _parse_iso_dt(end_row.value)
    finally:
        session.close()

    start_dt = _subtract_one_year(end_dt)
    start_iso = _format_dt_for_tql(start_dt)
    end_iso = _format_dt_for_tql(end_dt)

    query = "(dueDate >= '{start}') AND (dueDate <= '{end}')".format(
        start=start_iso,
        end=end_iso,
    )

    # 直接调用钉钉列表接口（并由 query_project_tasks_service 在成功后 upsert 到 A 表）
    query_payload = {
        "userId": user_id,
        "projectId": project_id,
        "query": query,
        "maxResults": max_results,
        "maxPages": max_pages,
        # 可选：强制刷新可由前端传入
        "force_refresh": bool(payload.get("force_refresh", False)),
    }

    list_res = query_project_tasks_service(query_payload)
    if not list_res.get("success"):
        return {
            "success": False,
            "error": list_res.get("error", "query project tasks failed"),
            "data": {},
        }

    ding = ((list_res.get("data") or {}).get("dingtalk")) or {}
    rows = ding.get("result") if isinstance(ding.get("result"), list) else []

    task_ids = set()
    for r in rows:
        if not isinstance(r, dict):
            continue
        sid = str(r.get("scenarioFieldConfigId") or r.get("scenariofieldconfigId") or "")
        if sid != DEFAULT_SCENARIO_FIELD_CONFIG_ID:
            continue
        tid = r.get("taskId")
        if tid:
            task_ids.add(str(tid))

    return {
        "success": True,
        "data": {
            "software_dev_task_count": len(task_ids),
            "start_time": start_iso,
            "end_time": end_iso,
            "projectId": str(project_id),
        },
    }

