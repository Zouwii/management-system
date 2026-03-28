"""
按执行者在服务端循环拉任务详情并汇总工时（单次 HTTP，避免浏览器 F12 出现大量请求）。
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional

from services.project_task_service import query_project_tasks_service, query_user_tasks_service
from services.workhour_util import parse_workhour_from_task_dict

DEFAULT_SCENARIO_FIELD_CONFIG_ID = "647854bcd999c893061ef8b5"


def _field_id(payload: Dict[str, Any]) -> str:
    return str(
        payload.get("workHourFieldId")
        or os.getenv("TB_TOOL_BT_WORKHOUR_FIELD_ID")
        or os.getenv("TB_TOOL_B1_WORKHOUR_FIELD_ID")
        or "64c8cad8485fb3987a5521b8"
)


def _task_scope_rows(
    rows: Any,
    scenario_id: str,
    executor_id: str,
) -> List[Dict[str, str]]:
    """列表里符合场景+执行者的任务，带列表接口返回的标题（与前端下拉中文一致）。"""
    if not isinstance(rows, list):
        return []
    seen = set()
    out: List[Dict[str, str]] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        sid = str(r.get("scenariofieldconfigId") or r.get("scenarioFieldConfigId") or "")
        if sid != scenario_id:
            continue
        if str(r.get("executorId") or "") != str(executor_id):
            continue
        tid = str(r.get("taskId") or "").strip()
        if not tid or tid in seen:
            continue
        seen.add(tid)
        title = str(r.get("content") or "").strip()
        out.append({"task_id": tid, "list_content": title})
    return out


def _parse_detail_item(ding: Any) -> Optional[Dict[str, Any]]:
    if isinstance(ding, list) and ding:
        x = ding[0] if isinstance(ding[0], dict) else None
        return x
    if isinstance(ding, dict):
        return ding
    return None


def executor_workhours_aggregate_service(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    拉项目任务列表 → 筛「软件开发」+ 指定执行者 → 逐个拉详情（服务端循环）→ 汇总工时字段。
    """
    payload = payload or {}
    user_id = str(payload.get("userId") or payload.get("userid") or "").strip()
    project_id = str(payload.get("projectId") or payload.get("projectid") or "").strip()
    executor_id = str(payload.get("executorId") or "").strip()
    if not user_id or not project_id:
        return {"success": False, "error": "missing userId or projectId", "data": {}}
    if not executor_id:
        return {"success": False, "error": "missing executorId", "data": {}}

    scenario_id = str(
        payload.get("scenarioFieldConfigId")
        or payload.get("scenarioFieldConfigID")
        or DEFAULT_SCENARIO_FIELD_CONFIG_ID
    )
    sleep_sec = float(payload.get("sleepSec", 0.12) or 0)
    max_tasks = int(payload.get("maxTasks", 300) or 300)
    if max_tasks < 1:
        max_tasks = 1
    if max_tasks > 500:
        max_tasks = 500

    list_payload: Dict[str, Any] = {
        "userId": user_id,
        "projectId": project_id,
        "query": payload.get("query", ""),
        "maxResults": int(payload.get("maxResults", 500) or 500),
        "maxPages": int(payload.get("maxPages", 20) or 20),
        "force_refresh": bool(payload.get("force_refresh_list", False)),
    }
    if payload.get("access_token"):
        list_payload["access_token"] = payload["access_token"]

    list_res = query_project_tasks_service(list_payload)
    if not list_res.get("success"):
        return {
            "success": False,
            "error": list_res.get("error", "project tasks query failed"),
            "data": list_res,
        }

    ding = ((list_res.get("data") or {}).get("dingtalk")) or {}
    rows = ding.get("result")
    task_scope = _task_scope_rows(rows, scenario_id, executor_id)
    if not task_scope:
        return {
            "success": True,
            "data": {
                "total_work_hour": 0.0,
                "executor_id": executor_id,
                "scenario_field_config_id": scenario_id,
                "task_count_in_scope": 0,
                "task_count_queried": 0,
                "task_count_with_hour": 0,
                "failures": [],
                "breakdown": [],
                "note": "列表中无匹配「软件开发」且执行者匹配的任务",
            },
        }

    if len(task_scope) > max_tasks:
        task_scope = task_scope[:max_tasks]

    field_id = _field_id(payload)
    failures: List[Dict[str, str]] = []
    breakdown: List[Dict[str, Any]] = []
    total = 0.0
    with_value = 0

    for i, spec in enumerate(task_scope):
        tid = spec["task_id"]
        list_content = str(spec.get("list_content") or "")
        q_payload: Dict[str, Any] = {
            "userId": user_id,
            "taskId": tid,
            "force_refresh": True,
        }
        if payload.get("parentTaskId"):
            q_payload["parentTaskId"] = payload.get("parentTaskId")
        if payload.get("access_token"):
            q_payload["access_token"] = payload["access_token"]

        dres = query_user_tasks_service(q_payload)
        if not dres.get("success"):
            failures.append(
                {"taskId": tid, "error": str(dres.get("error", "detail query failed"))}
            )
        else:
            raw = ((dres.get("data") or {}).get("dingtalk")) or {}
            item = _parse_detail_item(raw.get("result"))
            wh: Optional[float] = None
            title = ""
            if item:
                title = str(item.get("content") or "").strip()
                wh = parse_workhour_from_task_dict(item, field_id)
            if not title:
                title = list_content
            if wh is not None and wh == wh:  # not nan
                total += wh
                with_value += 1
            breakdown.append({"taskId": tid, "content": title, "work_hour": wh})

        if sleep_sec > 0 and i < len(task_scope) - 1:
            time.sleep(sleep_sec)

    total = round(total * 100) / 100

    return {
        "success": True,
        "data": {
            "total_work_hour": total,
            "work_hour_field_id": field_id,
            "executor_id": executor_id,
            "scenario_field_config_id": scenario_id,
            "task_count_in_scope": len(task_scope),
            "task_count_queried": len(task_scope),
            "task_count_with_hour": with_value,
            "failures": failures,
            "breakdown": breakdown,
        },
    }
