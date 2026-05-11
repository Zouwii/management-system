"""AI 创建 TB 任务单服务。

1.0 阶段先做“规则化模板创建”：AI/前端传入草稿，后端把草稿转换成
本体开发部软件开发任务模板，再调用钉钉创建任务接口。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import requests

from dingtalk_client import get_valid_access_token


# 默认模板来自现有本体开发部“软件开发”任务样例。
# 后续如果项目/列表/状态变化，优先从配置或前端 payload 覆盖这些默认值。
DEFAULT_AI_MISSION_TEMPLATE: Dict[str, Any] = {
    "projectId": "647854bc4a622b2e3199fa5a",
    "scenariofieldconfigId": "647854bcd999c893061ef8b5",
    "stageId": "647854bcd999c893061ef8a1",
    "tasklistId": "647854bcd999c893061ef898",
    "taskflowstatusId": "680a31478c1bdfc448d36ed0",
    "visible": "members",
    "priority": 0,
    "disableNotification": False,
    "disableActivity": False,
}

TASK_NATURE_CUSTOMFIELD_ID = "69d4d037c253ef42e9c31b38"
TASK_NATURE_OPTIONS: Dict[str, Dict[str, str]] = {
    "自主型": {"id": "69d4d037c253ef42e9c31b3a", "title": "自主型"},
    "指派型": {"id": "69d4d037c253ef42e9c31b39", "title": "指派型"},
    "能力建设型": {"id": "69d4d037c253ef42e9c31b3b", "title": "能力型"},
    "能力型": {"id": "69d4d037c253ef42e9c31b3b", "title": "能力型"},
}


def _clean_str(value: Any) -> str:
    return str(value or "").strip()


def _first_text(*values: Any) -> str:
    for value in values:
        text = _clean_str(value)
        if text:
            return text
    return ""


def _to_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _default_due_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        + timedelta(days=2)
    ).isoformat().replace("+00:00", "Z")


def _normalize_datetime_iso(value: Any, fallback: str) -> str:
    text = _clean_str(value)
    if not text:
        return fallback
    if text.endswith("Z"):
        return text
    try:
        dt = datetime.fromisoformat(text)
    except Exception:
        return text
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _to_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _build_note(draft: Dict[str, Any], payload: Dict[str, Any]) -> str:
    note = _first_text(payload.get("note"), draft.get("note"))
    requirement = _first_text(draft.get("requirementDesc"), payload.get("requirementDesc"))
    outputs = [str(x or "").strip() for x in _to_list(draft.get("outputs") or payload.get("outputs")) if str(x or "").strip()]
    parts: List[str] = []
    if note:
        parts.append(note)
    if requirement:
        parts.append("需求描述：\n{}".format(requirement))
    if outputs:
        parts.append("任务产出：\n{}".format("\n".join("- {}".format(item) for item in outputs)))
    return "\n\n".join(parts)


def _build_task_nature_customfield(draft: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    work_type = _first_text(payload.get("workType"), draft.get("workType"), payload.get("taskNature"), draft.get("taskNature"))
    option = TASK_NATURE_OPTIONS.get(work_type)
    if not option:
        return {}
    return {
        "_customfieldId": TASK_NATURE_CUSTOMFIELD_ID,
        "customFieldId": TASK_NATURE_CUSTOMFIELD_ID,
        "type": "dropDown",
        "values": [
            {
                "_id": option["id"],
                "customFieldValueId": option["id"],
                "title": option["title"],
            }
        ],
    }


def _build_customfields(draft: Dict[str, Any], payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw = payload.get("customfields") or payload.get("customFields") or draft.get("customfields") or draft.get("customFields")
    if isinstance(raw, list):
        return raw
    task_nature = _build_task_nature_customfield(draft, payload)
    return [task_nature] if task_nature else []


def _extract_created_task_id(data: Any) -> str:
    if not isinstance(data, dict):
        return ""
    for key in ("_id", "id", "taskId", "_taskId"):
        value = _clean_str(data.get(key))
        if value:
            return value
    result = data.get("result")
    if isinstance(result, dict):
        return _extract_created_task_id(result)
    return ""


def build_ai_mission_create_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """把 AI 草稿转换成钉钉创建任务 payload。"""
    payload = payload or {}
    draft = payload.get("draft") if isinstance(payload.get("draft"), dict) else payload
    template = dict(DEFAULT_AI_MISSION_TEMPLATE)
    if isinstance(payload.get("template"), dict):
        template.update(payload.get("template") or {})

    executor_id = _first_text(
        payload.get("executorId"),
        payload.get("executor_id"),
        draft.get("executorId"),
        draft.get("executor_id"),
        payload.get("userId"),
        payload.get("userid"),
    )
    content = _first_text(draft.get("title"), draft.get("content"), payload.get("content"), payload.get("title"))
    if not content:
        raise ValueError("missing task title/content")
    if not executor_id:
        raise ValueError("missing executorId/userId")

    involve_members = [
        _clean_str(x)
        for x in _to_list(payload.get("involveMembers") or draft.get("involveMembers") or [executor_id])
        if _clean_str(x)
    ]
    if executor_id not in involve_members:
        involve_members.insert(0, executor_id)

    due_date = _normalize_datetime_iso(
        payload.get("dueDate") or draft.get("dueDate") or draft.get("deadline"),
        _default_due_iso(),
    )
    start_date = _normalize_datetime_iso(payload.get("startDate") or draft.get("startDate"), _utc_now_iso())
    create_time = _normalize_datetime_iso(payload.get("createTime") or draft.get("createTime"), _utc_now_iso())

    create_payload: Dict[str, Any] = {
        "content": content,
        "note": _build_note(draft, payload),
        "priority": int(payload.get("priority", template.get("priority", 0)) or 0),
        "involveMembers": involve_members,
        "executorId": executor_id,
        "dueDate": due_date,
        "createTime": create_time,
        "startDate": start_date,
        "visible": _first_text(payload.get("visible"), template.get("visible"), "members"),
        "disableNotification": _to_bool(
            payload.get("disableNotification"),
            bool(template.get("disableNotification", False)),
        ),
        "disableActivity": _to_bool(
            payload.get("disableActivity"),
            bool(template.get("disableActivity", False)),
        ),
    }

    # 以下字段用于尽量贴近你给的真实任务模板；若钉钉接口不接受，联调时可在这里收敛字段名。
    template_field_map = {
        "projectId": ("projectId", "_projectId"),
        "scenariofieldconfigId": ("scenariofieldconfigId", "scenarioFieldConfigId", "_scenariofieldconfigId"),
        "stageId": ("stageId", "_stageId"),
        "tasklistId": ("tasklistId", "taskListId", "_tasklistId"),
        "taskflowstatusId": ("taskflowstatusId", "taskflowStatusId", "_taskflowstatusId"),
    }
    for output_key, aliases in template_field_map.items():
        value = ""
        for alias in aliases:
            value = _first_text(payload.get(alias), draft.get(alias), template.get(alias), template.get(output_key))
            if value:
                break
        if value:
            create_payload[output_key] = value

    customfields = _build_customfields(draft, payload)
    if customfields:
        create_payload["customfields"] = customfields

    tag_ids = payload.get("tagIds") or draft.get("tagIds")
    if isinstance(tag_ids, list):
        create_payload["tagIds"] = tag_ids

    return create_payload


def ai_create_mission_service(payload: Dict[str, Any]) -> Dict[str, Any]:
    """调用钉钉创建任务接口。"""
    payload = payload or {}
    user_id = _first_text(payload.get("userId"), payload.get("userid"), payload.get("creatorUserId"), payload.get("executorId"))
    if not user_id:
        return {"success": False, "error": "missing userId", "data": {}}

    token_result = get_valid_access_token(payload)
    if not token_result.get("ok"):
        return {
            "success": False,
            "error": token_result.get("error", "failed to get access token"),
            "data": token_result,
        }

    try:
        create_payload = build_ai_mission_create_payload(payload)
    except Exception as exc:
        return {"success": False, "error": str(exc), "data": {}}

    url = "https://api.dingtalk.com/v1.0/project/organizations/users/{}/tasks".format(user_id)
    try:
        resp = requests.post(
            url,
            json=create_payload,
            headers={
                "x-acs-dingtalk-access-token": token_result["access_token"],
                "Content-Type": "application/json",
            },
            timeout=30,
        )
        try:
            data = resp.json()
        except Exception:
            data = {"raw": resp.text}
        ok = 200 <= resp.status_code < 300
        task_id = _extract_created_task_id(data)
        return {
            "success": ok,
            "error": "" if ok else "dingtalk create task failed",
            "data": {
                "status_code": resp.status_code,
                "dingtalk": data,
                "taskId": task_id,
                "taskUrl": "https://www.teambition.com/task/{}".format(task_id) if task_id else "",
                "requestPayload": create_payload,
            },
            "meta": {
                "endpoint": "/api/bt/ai/create_mission",
                "dingtalk_url": url,
                "token_source": token_result.get("source"),
            },
        }
    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
            "data": {"requestPayload": create_payload},
        }
