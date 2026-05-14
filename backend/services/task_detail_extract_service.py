"""Read-only task detail extraction service.

This service reads `project_task_details` rows and extracts custom field
content without mutating any task data.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from db.engine import SessionLocal
from db.orm import ProjectTaskDetail
from services.task_sync_service import (
    REQUIREMENT_DESC_CUSTOMFIELD_ID,
    TASK_OUTPUT_CUSTOMFIELD_ID,
    _extract_custom_field_value_titles,
)


def _clean_str(value: Any) -> str:
    return str(value or "").strip()


def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _normalize_row(row: ProjectTaskDetail) -> Dict[str, Any]:
    raw_json = _as_dict(row.raw_json)
    custom_fields = row.custom_fields_json
    if not custom_fields:
        custom_fields = raw_json.get("customFields") or raw_json.get("customfields") or []

    requirement_desc = _extract_custom_field_value_titles(custom_fields, REQUIREMENT_DESC_CUSTOMFIELD_ID)
    task_outputs = _extract_custom_field_value_titles(custom_fields, TASK_OUTPUT_CUSTOMFIELD_ID)

    return {
        "projectId": _clean_str(row.project_id),
        "taskId": _clean_str(row.task_id),
        "queryUserId": _clean_str(row.query_user_id),
        "content": _clean_str(row.content),
        "dueDate": row.due_date.isoformat() if row.due_date else "",
        "parentTaskId": _clean_str(row.parent_task_id or row.parent_id),
        "taskListId": _clean_str(row.task_list_id),
        "taskStageId": _clean_str(row.task_stage_id),
        "taskNature": _clean_str(row.task_nature),
        "workdayCostHour": row.workday_costhour,
        "workHour": row.work_hour,
        "customFields": custom_fields if isinstance(custom_fields, list) else [],
        "requirementDesc": requirement_desc[0] if requirement_desc else "",
        "taskOutputs": task_outputs,
        "taskOutputText": "\n".join(task_outputs),
        "matchedCustomFields": {
            "requirementDesc": {
                "customFieldId": REQUIREMENT_DESC_CUSTOMFIELD_ID,
                "titles": requirement_desc,
            },
            "taskOutput": {
                "customFieldId": TASK_OUTPUT_CUSTOMFIELD_ID,
                "titles": task_outputs,
            },
        },
    }


def extract_task_detail_custom_fields_service(
    *,
    user_id: str,
    task_id: str,
    project_id: Optional[str] = None,
) -> Dict[str, Any]:
    user_id = _clean_str(user_id)
    task_id = _clean_str(task_id)
    project_id = _clean_str(project_id)
    if not user_id or not task_id:
        return {"success": False, "error": "missing userId or taskId", "data": {}}

    session = SessionLocal()
    try:
        query = session.query(ProjectTaskDetail).filter(
            ProjectTaskDetail.query_user_id == user_id,
            ProjectTaskDetail.task_id == task_id,
        )
        if project_id:
            query = query.filter(ProjectTaskDetail.project_id == project_id)
        row = query.order_by(ProjectTaskDetail.fetched_at.desc()).first()
        if not row:
            return {"success": False, "error": "task detail not found", "data": {}}
        return {
            "success": True,
            "data": _normalize_row(row),
            "meta": {
                "taskId": task_id,
                "userId": user_id,
                "projectId": project_id,
                "source": "project_task_details",
            },
        }
    except Exception as exc:
        return {"success": False, "error": str(exc), "data": {}}
    finally:
        session.close()
