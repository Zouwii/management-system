"""算法组两个项目的手动 A/B 全量同步。"""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select

from base.db.engine import AlgoSessionLocal
from base.db.orm import AlgoIssue, AlgoIssueDetail, AlgoTask, AlgoTaskDetail
from base.dingtalk_client import get_valid_access_token
from base.projects.task_service import query_project_tasks_service, query_user_tasks_service
from base.sync.task_sync import (
    DEFAULT_WORKHOUR_FIELD_ID,
    OVERDUE_TAG_ID,
    _apply_task_dict_to_orm,
    _extract_cascading_project_fields,
    _extract_detail_item,
    _extract_requirement_desc,
    _extract_task_nature,
    _extract_task_outputs,
    _extract_workday_costhour,
    _get_business_type_tag_mapping,
    _get_task_flow_status_mapping,
    _parse_iso_dt,
    _resolve_business_type_from_tags,
    _resolve_task_flow_status_id,
    _serialize_outputs,
    _str_list,
)
from workhour.personal.util import parse_workhour_from_task_dict


ALGO_PROJECTS = (
    {
        "name": "算法开发",
        "kind": "dev",
        "project_id": "636f343d3997deea0514c030",
        "scenario_field_config_id": "636f343df27cfe0042368b30",
    },
    {
        "name": "算法问题",
        "kind": "issue",
        "project_id": "636f31a87ef5737c3e837d00",
        "scenario_field_config_id": "636f31a8708ae400405aaaab",
    },
)

ALGO_MEMBER_IDS = (
    "0525436259671512",    # 刘丰
    "2464543025951000",    # 琚玲
    "555363695138848564",  # 高尔峰
    "22665556381168535",   # 邵京
    "2409506118778941",    # 庞涛
)

# groupmap 组在算法项目中使用的自定义字段。这些 ID 与本体开发部不同，
# 但落库语义和三级级联拆分口径保持一致。
GROUPMAP_WORK_HOUR_FIELD_ID = "660a2e656ee76e418ebdedd8"
GROUPMAP_WORKDAY_COSTHOUR_FIELD_ID = "665ee058c3f77d1e7d428b28"
GROUPMAP_NEED_STATISTIC_FIELD_ID = "667a63f6bf3f63bb20c86c8a"
GROUPMAP_CASCADING_PROJECT_FIELD_ID = "665ee053c3f77d1e7d4282ce"

ALGO_ISSUE_WORKDAY_COSTHOUR_FIELD_ID = "665ee06832288bab82e6b4fa"
ALGO_ISSUE_NEED_STATISTIC_FIELD_ID = "667a597bb146fd1f4c5b3d8e"
ALGO_ISSUE_CASCADING_PROJECT_FIELD_ID = "665ee06432288bab82e6adbe"


def _safe_json(value: Any) -> Optional[str]:
    try:
        return json.dumps(value, ensure_ascii=False)
    except Exception:
        return None


def _parse_int(value: Any) -> Optional[int]:
    if value is None or str(value) == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _custom_field_first_title(item: Dict[str, Any], field_id: str) -> Optional[str]:
    fields = item.get("customFields") or item.get("customfields") or []
    if not isinstance(fields, list):
        return None
    for field in fields:
        if not isinstance(field, dict):
            continue
        current_id = str(
            field.get("customFieldId") or field.get("customfieldId") or ""
        ).strip()
        if current_id != field_id:
            continue
        values = field.get("value")
        first = values[0] if isinstance(values, list) and values else values
        if isinstance(first, dict):
            first = first.get("value") if first.get("value") is not None else first.get("title")
        value = str(first or "").strip()
        return value or None
    return None


def _extract_groupmap_number(item: Dict[str, Any], field_id: str) -> Optional[float]:
    value = _custom_field_first_title(item, field_id)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_algo_cascading_fields(item: Dict[str, Any]) -> Dict[str, Optional[str]]:
    result = _extract_cascading_project_fields(item)

    cascading_title = (
        _custom_field_first_title(item, GROUPMAP_CASCADING_PROJECT_FIELD_ID)
        or _custom_field_first_title(item, ALGO_ISSUE_CASCADING_PROJECT_FIELD_ID)
    )
    if cascading_title:
        parts = [part.strip() for part in cascading_title.split("/")]
        result["project_category_1"] = parts[0] if len(parts) >= 1 and parts[0] else None
        result["vehicle_type_2"] = parts[1] if len(parts) >= 2 and parts[1] else None
        result["project_name_3"] = parts[2] if len(parts) >= 3 and parts[2] else None

    need_statistic = (
        _custom_field_first_title(item, GROUPMAP_NEED_STATISTIC_FIELD_ID)
        or _custom_field_first_title(item, ALGO_ISSUE_NEED_STATISTIC_FIELD_ID)
    )
    if need_statistic in ("是", "否"):
        result["need_statistic"] = need_statistic
    return result


def _extract_algo_work_hour(item: Dict[str, Any], fallback_field_id: str) -> Tuple[Optional[float], str]:
    value = _extract_groupmap_number(item, GROUPMAP_WORK_HOUR_FIELD_ID)
    if value is not None:
        return value, GROUPMAP_WORK_HOUR_FIELD_ID
    return parse_workhour_from_task_dict(item, fallback_field_id), fallback_field_id


def _extract_algo_workday_costhour(item: Dict[str, Any]) -> Optional[float]:
    value = _extract_groupmap_number(item, GROUPMAP_WORKDAY_COSTHOUR_FIELD_ID)
    if value is None:
        value = _extract_groupmap_number(item, ALGO_ISSUE_WORKDAY_COSTHOUR_FIELD_ID)
    return value if value is not None else _extract_workday_costhour(item)


def _fetch_project_member_tasks(
    access_token: str,
    user_id: str,
    project: Dict[str, str],
) -> Dict[str, Any]:
    result = query_project_tasks_service(
        {
            "userId": user_id,
            "projectId": project["project_id"],
            "access_token": access_token,
            "maxResults": 500,
            "maxPages": 200,
            "retries": 2,
        }
    )
    if not result.get("success"):
        return {
            "success": False,
            "user_id": user_id,
            "error": result.get("error", "project task query failed"),
            "tasks": [],
            "meta": result.get("meta") or {},
        }
    rows = ((result.get("data") or {}).get("dingtalk") or {}).get("result") or []
    scenario_id = project["scenario_field_config_id"]
    tasks = [
        row
        for row in rows
        if isinstance(row, dict)
        and str(row.get("scenariofieldconfigId") or row.get("scenarioFieldConfigId") or "")
        == scenario_id
    ]
    return {
        "success": True,
        "user_id": user_id,
        "tasks": tasks,
        "meta": result.get("meta") or {},
    }


def _upsert_a_rows(
    project: Dict[str, str],
    tasks_by_id: Dict[str, Dict[str, Any]],
    synced_at: datetime,
    reconcile: bool = False,
) -> int:
    model = AlgoTask if project["kind"] == "dev" else AlgoIssue
    session = AlgoSessionLocal()
    count = 0
    try:
        for task_id, item in tasks_by_id.items():
            stmt = select(model).where(
                model.project_id == project["project_id"],
                model.task_id == task_id,
            )
            row = session.scalars(stmt).first()
            if row is None:
                row = model()
                session.add(row)
            _apply_task_dict_to_orm(row, item, synced_at)
            # ProgramIssue 比 ProjectTask 多一个完成时间字段。
            if project["kind"] == "issue":
                row.accomplished_at = _parse_iso_dt(
                    item.get("accomplishTime") or item.get("accomplished")
                )
            count += 1
        if reconcile:
            current_ids = set(tasks_by_id)
            existing_rows = session.query(model).filter(
                model.project_id == project["project_id"]
            ).all()
            for row in existing_rows:
                if str(row.task_id) not in current_ids:
                    session.delete(row)
        session.commit()
        return count
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _fetch_detail(
    access_token: str,
    project_id: str,
    query_user_id: str,
    task_id: str,
) -> Dict[str, Any]:
    result = query_user_tasks_service(
        {
            "userId": query_user_id,
            "taskId": task_id,
            "projectId": project_id,
            "access_token": access_token,
            "force_refresh": True,
        }
    )
    item = _extract_detail_item(result) if result.get("success") else None
    return {
        "success": bool(result.get("success") and item),
        "query_user_id": query_user_id,
        "task_id": task_id,
        "item": item,
        "error": result.get("error") if not result.get("success") else (
            "empty dingtalk detail" if not item else ""
        ),
    }


def _apply_dev_detail(
    row: AlgoTaskDetail,
    *,
    project_id: str,
    query_user_id: str,
    task_id: str,
    item: Dict[str, Any],
    now: datetime,
    field_id: str,
    business_mapping: Dict[str, int],
    status_mapping: Dict[str, int],
) -> None:
    tag_ids = _str_list("tagIds", item)
    cfs = item.get("customFields") or item.get("customfields")
    cascading = _extract_algo_cascading_fields(item)
    work_hour, resolved_work_hour_field_id = _extract_algo_work_hour(item, field_id)
    parent_id = str(item.get("parentTaskId") or item.get("parent_id") or "") or None

    row.project_id = project_id
    row.task_id = task_id
    row.query_user_id = query_user_id
    row.scenario_field_config_id = str(
        item.get("scenarioFieldConfigId") or item.get("scenariofieldconfigId") or ""
    ) or None
    row.content = str(item.get("content") or "")
    row.due_date = _parse_iso_dt(item.get("dueDate"))
    row.work_hour_field_id = resolved_work_hour_field_id
    row.work_hour = work_hour
    row.custom_fields_json = cfs if cfs is not None else None
    row.raw_json = _safe_json(item)
    row.requirement_desc = _extract_requirement_desc(item)
    row.task_outputs = _serialize_outputs(_extract_task_outputs(item))
    row.parent_task_id = parent_id
    row.parent_id = parent_id
    row.task_list_id = str(item.get("taskListId") or "") or None
    row.task_stage_id = str(item.get("taskStageId") or item.get("stageId") or "") or None
    row.unique_id = _parse_int(item.get("uniqueId"))
    row.task_nature = _extract_task_nature(item)
    row.need_statistic = cascading["need_statistic"]
    row.workday_costhour = _extract_algo_workday_costhour(item)
    row.is_overdue = OVERDUE_TAG_ID in tag_ids
    row.business_type = _resolve_business_type_from_tags(tag_ids, business_mapping)
    row.task_flow_status_id = _resolve_task_flow_status_id(item, status_mapping)
    row.project_category_1 = cascading["project_category_1"]
    row.vehicle_type_2 = cascading["vehicle_type_2"]
    row.project_name_3 = cascading["project_name_3"]
    row.fetched_at = now


def _apply_issue_detail(
    row: AlgoIssueDetail,
    *,
    project_id: str,
    query_user_id: str,
    task_id: str,
    item: Dict[str, Any],
    now: datetime,
    field_id: str,
    business_mapping: Dict[str, int],
) -> None:
    tag_ids = _str_list("tagIds", item)
    cfs = item.get("customFields") or item.get("customfields")
    cascading = _extract_algo_cascading_fields(item)
    work_hour, resolved_work_hour_field_id = _extract_algo_work_hour(item, field_id)

    row.project_id = project_id
    row.task_id = task_id
    row.query_user_id = query_user_id
    row.scenario_field_config_id = str(
        item.get("scenarioFieldConfigId") or item.get("scenariofieldconfigId") or ""
    )
    row.content = str(item.get("content") or "")
    row.executor_id = str(item.get("executorId") or "")
    row.creator_id = str(item.get("creatorId") or "")
    row.task_list_id = str(item.get("taskListId") or "") or None
    row.task_stage_id = str(item.get("taskStageId") or item.get("stageId") or "") or None
    row.taskflow_status_id = str(
        item.get("taskflowStatusId") or item.get("taskflowstatusId") or ""
    ) or None
    row.unique_id = _parse_int(item.get("uniqueId"))
    row.parent_id = str(item.get("parentTaskId") or item.get("parent_id") or "") or None
    row.task_nature = _extract_task_nature(item)
    row.need_statistic = cascading["need_statistic"]
    row.workday_costhour = _extract_algo_workday_costhour(item)
    row.work_hour_field_id = resolved_work_hour_field_id
    row.work_hour = work_hour
    row.business_type = _resolve_business_type_from_tags(tag_ids, business_mapping)
    row.is_archived = bool(item.get("isArchived"))
    row.is_done = bool(item.get("isDone"))
    row.priority = _parse_int(item.get("priority"))
    row.visible = str(item.get("visible") or "") or None
    row.created_at_ding = _parse_iso_dt(item.get("created"))
    row.updated_at_ding = _parse_iso_dt(item.get("updated"))
    row.ancestor_ids = _str_list("ancestorIds", item) or None
    row.involve_members = _str_list("involveMembers", item) or None
    row.tag_ids = tag_ids or None
    row.custom_fields_json = cfs if cfs is not None else None
    row.raw_json = _safe_json(item)
    row.project_category_1 = cascading["project_category_1"]
    row.vehicle_type_2 = cascading["vehicle_type_2"]
    row.project_name_3 = cascading["project_name_3"]
    row.fetched_at = now


def _upsert_detail_rows(
    project: Dict[str, str],
    detail_results: List[Dict[str, Any]],
    synced_at: datetime,
    reconcile: bool = False,
) -> int:
    model = AlgoTaskDetail if project["kind"] == "dev" else AlgoIssueDetail
    field_id = str(os.getenv("TB_TOOL_BT_WORKHOUR_FIELD_ID") or DEFAULT_WORKHOUR_FIELD_ID)
    business_mapping = _get_business_type_tag_mapping()
    status_mapping = _get_task_flow_status_mapping()
    session = AlgoSessionLocal()
    count = 0
    try:
        for result in detail_results:
            item = result.get("item")
            if not result.get("success") or not isinstance(item, dict):
                continue
            task_id = result["task_id"]
            query_user_id = result["query_user_id"]
            stmt = select(model).where(
                model.task_id == task_id,
                model.query_user_id == query_user_id,
            )
            row = session.scalars(stmt).first()
            if row is None:
                row = model(
                    project_id=project["project_id"],
                    task_id=task_id,
                    query_user_id=query_user_id,
                )
                session.add(row)
            if project["kind"] == "dev":
                _apply_dev_detail(
                    row,
                    project_id=project["project_id"],
                    query_user_id=query_user_id,
                    task_id=task_id,
                    item=item,
                    now=synced_at,
                    field_id=field_id,
                    business_mapping=business_mapping,
                    status_mapping=status_mapping,
                )
            else:
                _apply_issue_detail(
                    row,
                    project_id=project["project_id"],
                    query_user_id=query_user_id,
                    task_id=task_id,
                    item=item,
                    now=synced_at,
                    field_id=field_id,
                    business_mapping=business_mapping,
                )
            count += 1
        if reconcile:
            current_keys = {
                (str(item["task_id"]), str(item["query_user_id"]))
                for item in detail_results
                if item.get("success") and isinstance(item.get("item"), dict)
            }
            existing_rows = session.query(model).filter(
                model.project_id == project["project_id"]
            ).all()
            for row in existing_rows:
                key = (str(row.task_id), str(row.query_user_id))
                if key not in current_keys:
                    session.delete(row)
        session.commit()
        return count
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _sync_project(access_token: str, project: Dict[str, str], thread_count: int) -> Dict[str, Any]:
    tasks_by_id: Dict[str, Dict[str, Any]] = {}
    list_fetched = 0
    errors: List[Dict[str, Any]] = []
    list_pages = 0

    for user_id in ALGO_MEMBER_IDS:
        result = _fetch_project_member_tasks(access_token, user_id, project)
        if not result.get("success"):
            errors.append({"phase": "list", "userId": user_id, "error": result.get("error")})
            continue
        list_pages += int((result.get("meta") or {}).get("page_count") or 0)
        for item in result.get("tasks") or []:
            list_fetched += 1
            task_id = str(item.get("taskId") or "")
            if not task_id:
                continue
            tasks_by_id.setdefault(task_id, item)

    now = datetime.now(timezone.utc)
    list_complete = not errors
    a_upserted = _upsert_a_rows(
        project, tasks_by_id, now, reconcile=list_complete
    )

    # 与本体同步一致：A 表跨查询成员去重后，以任务 executor 作为
    # B 表 query_user_id；只拉算法组五位成员实际负责的任务。
    detail_specs: Dict[Tuple[str, str], None] = {}
    allowed_executors = set(ALGO_MEMBER_IDS)
    for task_id, item in tasks_by_id.items():
        executor_id = str(item.get("executorId") or "").strip()
        if executor_id in allowed_executors:
            detail_specs[(executor_id, task_id)] = None

    detail_results: List[Dict[str, Any]] = []
    workers = max(1, min(int(thread_count or 1), 8))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        future_map = {
            pool.submit(
                _fetch_detail,
                access_token,
                project["project_id"],
                query_user_id,
                task_id,
            ): (query_user_id, task_id)
            for query_user_id, task_id in detail_specs
        }
        for future in as_completed(future_map):
            query_user_id, task_id = future_map[future]
            try:
                result = future.result()
            except Exception as exc:
                result = {
                    "success": False,
                    "query_user_id": query_user_id,
                    "task_id": task_id,
                    "error": str(exc),
                }
            detail_results.append(result)
            if not result.get("success"):
                errors.append(
                    {
                        "phase": "detail",
                        "userId": query_user_id,
                        "taskId": task_id,
                        "error": result.get("error"),
                    }
                )

    b_upserted = _upsert_detail_rows(
        project,
        detail_results,
        now,
        reconcile=list_complete and not errors,
    )
    return {
        "projectId": project["project_id"],
        "scenarioFieldConfigId": project["scenario_field_config_id"],
        "listPages": list_pages,
        "listFetched": list_fetched,
        "uniqueTasks": len(tasks_by_id),
        "algorithmExecutorTasks": len(detail_specs),
        "aUpserted": a_upserted,
        "detailFetched": sum(1 for item in detail_results if item.get("success")),
        "bUpserted": b_upserted,
        "failed": len(errors),
        "errors": errors[:100],
    }


def sync_algo_all(payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """手动同步算法开发、算法问题两个项目的四张 A/B 表。"""
    payload = dict(payload or {})
    token_result = get_valid_access_token(payload)
    if not token_result.get("ok"):
        return {
            "success": False,
            "error": token_result.get("error", "failed to get access token"),
            "data": {},
        }
    thread_count = int(payload.get("thread_count", 5) or 5)
    projects: Dict[str, Dict[str, Any]] = {}
    fatal_errors: List[Dict[str, Any]] = []
    for project in ALGO_PROJECTS:
        try:
            projects[project["name"]] = _sync_project(
                token_result["access_token"], project, thread_count
            )
        except Exception as exc:
            fatal_errors.append({"project": project["name"], "error": str(exc)})
            projects[project["name"]] = {
                "projectId": project["project_id"],
                "failed": 1,
                "errors": [{"phase": "database", "error": str(exc)}],
            }
    return {
        "success": not fatal_errors,
        "error": "; ".join(item["error"] for item in fatal_errors),
        "data": {
            "syncedAt": datetime.now(timezone.utc).isoformat(),
            "memberCount": len(ALGO_MEMBER_IDS),
            "projects": projects,
            "fatalErrors": fatal_errors,
        },
    }


if __name__ == "__main__":
    print(json.dumps(sync_algo_all(), ensure_ascii=False, indent=2))
