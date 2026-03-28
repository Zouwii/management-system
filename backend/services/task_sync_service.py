"""
将钉钉查询结果落库：A 表列表、B 表明细（模式 1 覆盖）。
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select

from db.engine import SessionLocal
from db.orm import ProjectTask, ProjectTaskDetail
from services.project_task_service import query_project_tasks_service, query_user_tasks_service
from services.workhour_util import parse_workhour_from_task_dict

DEFAULT_SCENARIO_FIELD_CONFIG_ID = "647854bcd999c893061ef8b5"  # 软件开发
DEFAULT_WORKHOUR_FIELD_ID = "64c8cad8485fb3987a5521b8"


def _parse_iso_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    t = str(s).strip()
    if not t:
        return None
    if t.endswith("Z"):
        t = t[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(t)
    except ValueError:
        return None


def _customfield_id_list(d: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    for cf in d.get("customfields") or d.get("customFields") or []:
        if not isinstance(cf, dict):
            continue
        cid = cf.get("customfieldId") or cf.get("customFieldId")
        if cid:
            out.append(str(cid))
    return out


def _str_list(key: str, d: Dict[str, Any]) -> List[str]:
    v = d.get(key)
    if not isinstance(v, list):
        return []
    return [str(x) for x in v if x is not None]


def _apply_task_dict_to_orm(obj: ProjectTask, d: Dict[str, Any], list_synced_at: datetime) -> None:
    obj.task_id = str(d.get("taskId") or "")
    obj.project_id = str(d.get("projectId") or "")
    obj.content = str(d.get("content") or "")
    obj.scenario_field_config_id = str(
        d.get("scenariofieldconfigId") or d.get("scenarioFieldConfigId") or ""
    )
    obj.stage_id = str(d.get("stageId") or d.get("taskStageId") or "")
    obj.taskflow_status_id = str(
        d.get("taskflowstatusId") or d.get("taskflowStatusId") or ""
    )
    obj.executor_id = str(d.get("executorId") or "")
    obj.creator_id = str(d.get("creatorId") or "")
    obj.due_date = _parse_iso_dt(d.get("dueDate"))
    obj.ding_created = _parse_iso_dt(d.get("created"))
    obj.ding_updated = _parse_iso_dt(d.get("updated"))
    obj.note = str(d.get("note") or "")
    obj.priority = int(d.get("priority") or 0)
    obj.progress = int(d.get("progress") or 0)
    obj.visible = str(d.get("visible") or "members")
    obj.is_archived = bool(d.get("isArchived"))
    obj.is_deleted = bool(d.get("isDeleted"))
    obj.is_done = bool(d.get("isDone"))
    obj.ancestor_ids = _str_list("ancestorIds", d) or None
    obj.involve_members = _str_list("involveMembers", d) or None
    obj.tag_ids = _str_list("tagIds", d) or None
    labels = d.get("labels")
    obj.labels = labels if isinstance(labels, list) else None
    ids = _customfield_id_list(d)
    obj.customfield_ids = ids or None
    try:
        obj.raw_json = json.dumps(d, ensure_ascii=False)
    except Exception:
        obj.raw_json = None
    obj.list_synced_at = list_synced_at


def _upsert_filtered_project_tasks(
    payload: Dict[str, Any], query_result: Dict[str, Any]
) -> Dict[str, Any]:
    """
    从已成功返回的 query_project_tasks_service 结果中按 scenario 过滤并 upsert A 表。
    """
    scenario_id = str(
        payload.get("scenarioFieldConfigId")
        or payload.get("scenarioFieldConfigID")
        or DEFAULT_SCENARIO_FIELD_CONFIG_ID
    )

    ding = (query_result.get("data") or {}).get("dingtalk") or {}
    all_rows = ding.get("result") if isinstance(ding.get("result"), list) else []
    filtered: List[Dict[str, Any]] = []
    for r in all_rows:
        if not isinstance(r, dict):
            continue
        sid = str(r.get("scenariofieldconfigId") or r.get("scenarioFieldConfigId") or "")
        if sid == scenario_id:
            filtered.append(r)

    now = datetime.now(timezone.utc)
    session = SessionLocal()
    upserted = 0
    try:
        for d in filtered:
            pid = str(d.get("projectId") or "")
            tid = str(d.get("taskId") or "")
            if not pid or not tid:
                continue
            stmt = select(ProjectTask).where(
                ProjectTask.project_id == pid,
                ProjectTask.task_id == tid,
            )
            existing = session.scalars(stmt).first()
            if existing:
                _apply_task_dict_to_orm(existing, d, now)
            else:
                row = ProjectTask()
                _apply_task_dict_to_orm(row, d, now)
                session.add(row)
            upserted += 1
        session.commit()
    except Exception as e:
        session.rollback()
        return {"success": False, "error": str(e), "data": {}}
    finally:
        session.close()

    return {
        "success": True,
        "data": {
            "upserted": upserted,
            "filtered_count": len(filtered),
            "fetched_count": len(all_rows),
            "scenario_field_config_id": scenario_id,
            "list_synced_at": now.isoformat(),
            "meta": query_result.get("meta") or {},
        },
    }


def sync_project_tasks_to_db(
    payload: Dict[str, Any], query_result: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    拉项目任务列表并 upsert A 表；仅保留 scenarioFieldConfigId 匹配的行。
    请求体与 /api/bt/query_project_tasks 相同，额外可传：
    - scenarioFieldConfigId：默认软件开发

    若传入 query_result（已成功调用的 query_project_tasks_service 返回值），则不再请求钉钉，
    直接过滤并写入 A 表（供 /query_project_tasks 合并调用）。
    """
    payload = dict(payload or {})
    query_payload = {
        k: v
        for k, v in payload.items()
        if k not in ("scenarioFieldConfigId", "scenarioFieldConfigID")
    }
    if query_result is None:
        query_result = query_project_tasks_service(query_payload)
        if not query_result.get("success"):
            return {
                "success": False,
                "error": query_result.get("error", "dingtalk project tasks query failed"),
                "data": query_result,
            }
    return _upsert_filtered_project_tasks(payload, query_result)


def sync_task_detail_to_db(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    拉单任务详情并 upsert B 表（模式 1）。
    请求体与 /api/bt/query_task_details 类似，额外可传：
    - projectId：可选，写入 B 表；若缺省则用钉钉返回的 projectId
    - workHourFieldId：默认环境变量 TB_TOOL_BT_WORKHOUR_FIELD_ID（或旧 TB_TOOL_B1_*）或内置默认
    """
    payload = dict(payload or {})
    user_id = str(payload.get("userId") or payload.get("userid") or "")
    task_id = str(payload.get("taskId") or "")
    if not user_id or not task_id:
        return {"success": False, "error": "missing userId or taskId", "data": {}}

    field_id = str(
        payload.get("workHourFieldId")
        or os.getenv("TB_TOOL_BT_WORKHOUR_FIELD_ID")
        or os.getenv("TB_TOOL_B1_WORKHOUR_FIELD_ID")
        or DEFAULT_WORKHOUR_FIELD_ID
    )
    project_id_hint = str(payload.get("projectId") or payload.get("projectid") or "")

    q_payload = {
        "userId": user_id,
        "taskId": task_id,
        "parentTaskId": payload.get("parentTaskId", ""),
        "force_refresh": bool(payload.get("force_refresh", True)),
    }
    if payload.get("access_token"):
        q_payload["access_token"] = payload.get("access_token")

    result = query_user_tasks_service(q_payload)
    if not result.get("success"):
        return {
            "success": False,
            "error": result.get("error", "dingtalk task query failed"),
            "data": result,
        }

    ding = (result.get("data") or {}).get("dingtalk") or {}
    raw_result = ding.get("result")
    item: Optional[Dict[str, Any]] = None
    if isinstance(raw_result, list) and raw_result:
        item = raw_result[0] if isinstance(raw_result[0], dict) else None
    elif isinstance(raw_result, dict):
        item = raw_result

    if not item:
        return {
            "success": False,
            "error": "empty dingtalk result",
            "data": result,
        }

    project_id = project_id_hint or str(item.get("projectId") or "")
    if not project_id:
        return {"success": False, "error": "missing projectId in response and payload", "data": result}

    wh = parse_workhour_from_task_dict(item, field_id)
    cfs = item.get("customFields") or item.get("customfields")
    try:
        raw_blob = json.dumps(item, ensure_ascii=False)
    except Exception:
        raw_blob = None

    uid_val = item.get("uniqueId")
    unique_id: Optional[int]
    try:
        unique_id = int(uid_val) if uid_val is not None and str(uid_val) != "" else None
    except (TypeError, ValueError):
        unique_id = None

    now = datetime.now(timezone.utc)
    session = SessionLocal()
    try:
        stmt = select(ProjectTaskDetail).where(
            ProjectTaskDetail.task_id == task_id,
            ProjectTaskDetail.query_user_id == user_id,
        )
        row = session.scalars(stmt).first()
        if row:
            row.project_id = project_id
            row.work_hour_field_id = field_id
            row.work_hour = wh
            row.custom_fields_json = cfs if cfs is not None else None
            row.raw_json = raw_blob
            row.parent_task_id = str(item.get("parentTaskId") or "") or None
            row.task_list_id = str(item.get("taskListId") or "") or None
            row.task_stage_id = str(item.get("taskStageId") or item.get("stageId") or "") or None
            row.unique_id = unique_id
            row.fetched_at = now
        else:
            session.add(
                ProjectTaskDetail(
                    project_id=project_id,
                    task_id=task_id,
                    query_user_id=user_id,
                    work_hour_field_id=field_id,
                    work_hour=wh,
                    custom_fields_json=cfs if cfs is not None else None,
                    raw_json=raw_blob,
                    parent_task_id=str(item.get("parentTaskId") or "") or None,
                    task_list_id=str(item.get("taskListId") or "") or None,
                    task_stage_id=str(item.get("taskStageId") or item.get("stageId") or "") or None,
                    unique_id=unique_id,
                    fetched_at=now,
                )
            )
        session.commit()
    except Exception as e:
        session.rollback()
        return {"success": False, "error": str(e), "data": {}}
    finally:
        session.close()

    return {
        "success": True,
        "data": {
            "task_id": task_id,
            "query_user_id": user_id,
            "project_id": project_id,
            "work_hour": wh,
            "work_hour_field_id": field_id,
            "fetched_at": now.isoformat(),
            "meta": result.get("meta") or {},
        },
    }


def sync_task_details_batch_to_db(payload: Dict[str, Any]) -> Dict[str, Any]:
    """对 taskIds 逐个调用 sync_task_detail_to_db。"""
    payload = dict(payload or {})
    user_id = str(payload.get("userId") or payload.get("userid") or "")
    task_ids = payload.get("taskIds") or []
    if not user_id:
        return {"success": False, "error": "missing userId", "data": {}}
    if not isinstance(task_ids, list) or not task_ids:
        return {"success": False, "error": "missing taskIds (non-empty array)", "data": {}}

    sleep_sec = float(payload.get("sleepSec", 0) or 0)
    project_id_default = str(payload.get("projectId") or "")

    results: List[Dict[str, Any]] = []
    ok_count = 0
    for tid in task_ids:
        tid_s = str(tid).strip()
        if not tid_s:
            continue
        one = {
            "userId": user_id,
            "taskId": tid_s,
            "projectId": project_id_default,
            "parentTaskId": payload.get("parentTaskId", ""),
            "workHourFieldId": payload.get("workHourFieldId"),
            "force_refresh": payload.get("force_refresh", True),
        }
        if payload.get("access_token"):
            one["access_token"] = payload.get("access_token")
        r = sync_task_detail_to_db(one)
        results.append({"taskId": tid_s, "success": r.get("success"), "data": r.get("data"), "error": r.get("error")})
        if r.get("success"):
            ok_count += 1
        if sleep_sec > 0:
            time.sleep(sleep_sec)

    return {
        "success": True,
        "data": {
            "total": len(results),
            "ok_count": ok_count,
            "results": results,
        },
    }
