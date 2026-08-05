"""Teambition task creation service.

Builds and sends DingTalk create-task requests in the format:

  POST /v1.0/project/users/{userId}/tasks
  {
    "projectId": "String",
    "content": "String",
    "executorId": "String",
    "dueDate": "String",
    "note": "String",
    "priority": Integer,
    "customfields": [{
      "customfieldName": "String",
      "customfieldId": "String",
      "value": [{"title": "String"}]
    }],
    "stageId": "String",
    "parentTaskId": "String",
    "scenariofieldconfigId": "String",
    "startDate": "String",
    "visible": "String"
  }
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

CHINA_TZ = ZoneInfo("Asia/Shanghai")

import requests

from base.dingtalk_client import get_valid_access_token


# ── helpers ────────────────────────────────────────────────────

def _str(value: Any) -> str:
    return str(value or "").strip()


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _iso_fmt(value: str) -> str:
    """Normalize an ISO datetime string to DingTalk format (UTC Z).

    Naive datetimes (no timezone) are treated as Asia/Shanghai time (UTC+8)
    and converted to UTC before sending to the API.
    """
    if not value:
        return ""
    v = value.strip()
    if v.endswith("Z"):
        return v
    try:
        dt = datetime.fromisoformat(v)
    except (ValueError, TypeError):
        # Handle date-only input (e.g. "2026-05-30")
        try:
            from datetime import date
            d = date.fromisoformat(v)
            dt = datetime(d.year, d.month, d.day, tzinfo=CHINA_TZ)
            return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            return v
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=CHINA_TZ)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── custom field IDs ──────────────────────────────────────────

CUSTOMFIELD_REQUIREMENT = "686273700d15b3f835491a2e"   # 需求描述 (rtf)
CUSTOMFIELD_TASK_NATURE = "69d4d037c253ef42e9c31b38"   # 任务性质 (dropDown)
CUSTOMFIELD_OUTPUTS     = "6862737e3b781c68b3181925"   # 任务产出 (rtf)


# ── payload builder ────────────────────────────────────────────

def build_payload(draft: Dict[str, Any], template: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Build the DingTalk create-task request body from an AI task draft.

    Args:
        draft: Task draft with keys like title, workType, requirementDesc,
               outputs, dueDate, startDate, executorId, projectId, etc.
        template: Override defaults for projectId, stageId, etc.

    Returns:
        Dict ready to POST to the DingTalk API.
    """
    tpl = dict(template or {})

    content = _str(draft.get("title") or draft.get("content"))
    if not content:
        raise ValueError("missing task title")

    executor_id = _str(
        draft.get("executorId") or draft.get("executor_id")
        or draft.get("userId") or draft.get("userid")
    )
    if not executor_id:
        raise ValueError("missing executorId/userId")

    # ── custom fields ─────────────────────────────────────────
    customfields: List[Dict[str, Any]] = []

    # 1) Requirement description (rtf)
    req = _str(draft.get("requirementDesc"))
    if req:
        customfields.append({
            "customfieldName": "需求描述",
            "customfieldId": CUSTOMFIELD_REQUIREMENT,
            "value": [{"title": req}],
        })

    # 2) Task nature — workType (dropDown)
    work_type = _str(draft.get("workType") or draft.get("taskNature"))
    if work_type:
        customfields.append({
            "customfieldName": "任务性质",
            "customfieldId": CUSTOMFIELD_TASK_NATURE,
            "value": [{"title": work_type}],
        })

    # 3) Outputs
    outputs = draft.get("outputs") or []
    if isinstance(outputs, list) and outputs:
        valid = [_str(o) for o in outputs if _str(o)]
        if valid:
            cleaned = [item.rstrip() for item in valid]
            numbered = "\n".join(f"{i+1}. {item}" for i, item in enumerate(cleaned))
            customfields.append({
                "customfieldName": "任务产出",
                "customfieldId": CUSTOMFIELD_OUTPUTS,
                "value": [{"title": numbered}],
            })

    # ── payload ──────────────────────────────────────────────
    payload: Dict[str, Any] = {
        "projectId": _str(tpl.get("projectId") or "647854bc4a622b2e3199fa5a"),
        "content": content,
        "executorId": executor_id,
        "dueDate": _iso_fmt(_str(draft.get("dueDate"))),
        "note": "",
        "priority": _int(draft.get("priority"), 0),
        "stageId": _str(tpl.get("stageId") or "647854bcd999c893061ef8a1"),
        "scenariofieldconfigId": _str(tpl.get("scenariofieldconfigId") or "647854bcd999c893061ef8b5"),
        "startDate": _iso_fmt(_str(draft.get("startDate"))),
        "visible": _str(draft.get("visible") or "members"),
    }

    if customfields:
        payload["customfields"] = customfields

    parent = _str(draft.get("parentTaskId"))
    if parent:
        payload["parentTaskId"] = parent

    return payload


# ── API call ───────────────────────────────────────────────────

def create_task(draft: Dict[str, Any], template: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Create a Teambition task via the DingTalk API.

    Args:
        draft: Task draft fields (title, workType, requirementDesc, outputs, etc.).
               Must include either executorId or userId (DingTalk user ID).
        template: Optional template to override project defaults.

    Returns:
        Dict with keys: success, error, data (taskId, taskUrl, requestPayload).
    """
    draft = draft or {}

    user_id = _str(
        draft.get("userId") or draft.get("userid")
        or draft.get("executorId") or draft.get("executor_id")
    )
    if not user_id:
        return {"success": False, "error": "missing userId", "data": {}}

    # Get access token
    token_result = get_valid_access_token(draft)
    if not token_result.get("ok"):
        return {
            "success": False,
            "error": token_result.get("error", "failed to get access token"),
            "data": token_result,
        }

    # Build request payload
    try:
        req_body = build_payload(draft, template)
    except ValueError as exc:
        return {"success": False, "error": str(exc), "data": {}}

    # Call DingTalk API
    url = f"https://api.dingtalk.com/v1.0/project/users/{user_id}/tasks"
    try:
        from base.api_monitor import check_api_allowed
        if not check_api_allowed():
            return {"success": False, "error": "daily API limit reached", "data": {}}

        _start = time.time()
        resp = requests.post(
            url,
            json=req_body,
            headers={
                "x-acs-dingtalk-access-token": token_result["access_token"],
                "Content-Type": "application/json",
            },
            timeout=30,
        )
        _elapsed = int((time.time() - _start) * 1000)
        try:
            from base.api_monitor import record_api_call
            record_api_call("/v1.0/project/users/{userId}/tasks", resp.status_code, _elapsed, source="tb_create")
        except Exception:
            pass
        try:
            data = resp.json()
        except Exception:
            data = {"raw": resp.text}

        ok_flag = 200 <= resp.status_code < 300
        task_id = _str(
            data.get("_id") or data.get("id")
            or (data.get("result") or {}).get("taskId")
            or (data.get("result") or {}).get("_id")
        )
        return {
            "success": ok_flag,
            "error": "" if ok_flag else f"dingtalk API error (HTTP {resp.status_code})",
            "data": {
                "statusCode": resp.status_code,
                "taskId": task_id,
                "taskUrl": f"https://www.teambition.com/task/{task_id}" if task_id else "",
                "response": data,
                "requestPayload": req_body,
            },
        }
    except requests.RequestException as exc:
        return {
            "success": False,
            "error": str(exc),
            "data": {"requestPayload": req_body},
        }
