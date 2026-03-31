"""
将钉钉查询结果落库：A 表列表、B 表明细（模式 1 覆盖）。
"""

from __future__ import annotations

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select

from db.engine import SessionLocal
from db.orm import Config as DbConfig
from db.orm import ProjectTask, ProjectTaskDetail, ProjectTaskOverdueDetail
from services.project_task_service import query_project_tasks_service, query_user_tasks_service
from services.workhour_util import parse_workhour_from_task_dict
from dingtalk_client import get_valid_access_token

DEFAULT_SCENARIO_FIELD_CONFIG_ID = "647854bcd999c893061ef8b5"  # 软件开发
DEFAULT_WORKHOUR_FIELD_ID = "64c8cad8485fb3987a5521b8"
OVERDUE_TAG_ID = "6527846cb6be8066fe331fd0"


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


def all_time_download_service(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    all_time_download：按 config.end_time 算最近一年窗口
    1) 写入 A 表（project_tasks，软件开发场景）
    2) 3 线程轮循拉任务详情并写入 B 表（project_task_details）
    3) B 表写入按 config.start_time/end_time 的阈值窗口过滤
    4) B 表先对当前 project_id 全量删除，再由线程重新插入（避免 overdue 残留）

    输入：
    - userId / userid：用于调用钉钉列表接口的 userId（必填）
    - projectId / projectid：项目 ID（必填）
    - maxResults（可选，默认 500）
    - maxPages（可选，默认 200，最大 2000）
    """

    payload = dict(payload or {})
    user_id = str(payload.get("userId") or payload.get("userid") or "").strip()
    project_id = str(payload.get("projectId") or payload.get("projectid") or "").strip()
    if not user_id or not project_id:
        return {"success": False, "error": "missing userId or projectId", "data": {}}

    max_results = int(payload.get("maxResults", 500) or 500)
    max_pages = int(payload.get("maxPages", 200) or 200)
    if max_results < 1:
        max_results = 1
    if max_pages < 1:
        max_pages = 1
    if max_pages > 2000:
        max_pages = 2000

    def _cmp_dt(dt: Optional[datetime]) -> Optional[datetime]:
        if dt is None:
            return None
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    def _subtract_one_year(dt: datetime) -> datetime:
        # 处理 2/29：若替换失败，则落到 2/28
        try:
            return dt.replace(year=dt.year - 1)
        except ValueError:
            day = min(dt.day, 28)
            return dt.replace(year=dt.year - 1, day=day)

    def _format_dt_for_tql(dt: datetime) -> str:
        d = dt.astimezone(timezone.utc).replace(microsecond=0)
        # 参考前端/旧实现：固定 ".000Z"
        return d.strftime("%Y-%m-%dT%H:%M:%S") + ".000Z"

    # 1) 读取 config.end_time，算最近一年窗口并写入 A 表
    from db.orm import Config as DbConfig

    session = SessionLocal()
    try:
        end_row = session.query(DbConfig).filter(DbConfig.type_ == "end_time").first()
        start_row_cfg = session.query(DbConfig).filter(DbConfig.type_ == "start_time").first()
        end_row_cfg = end_row
    finally:
        session.close()

    if not end_row:
        return {"success": False, "error": "missing config end_time", "data": {}}

    end_dt = _cmp_dt(_parse_iso_dt(end_row.value))
    if not end_dt:
        return {"success": False, "error": "invalid config end_time", "data": {}}

    start_dt = _subtract_one_year(end_dt)
    start_iso = _format_dt_for_tql(start_dt)
    end_iso = _format_dt_for_tql(end_dt)

    query = "(dueDate >= '{start}') AND (dueDate <= '{end}')".format(start=start_iso, end=end_iso)

    dl_payload = dict(payload)
    dl_payload["userId"] = user_id
    dl_payload["projectId"] = project_id
    dl_payload["query"] = query
    dl_payload["maxResults"] = max_results
    dl_payload["maxPages"] = max_pages
    dl_payload["force_refresh"] = True

    sync_out = sync_project_tasks_to_db(dl_payload)
    if not sync_out.get("success"):
        return sync_out

    # 2) 从 A 表取出要轮循拉详情的 task 列表（软件开发 + 最近一年窗口）
    # 同时：计算 B 表写入用的阈值窗口（config.start_time/end_time）
    cfg_start_dt = _cmp_dt(_parse_iso_dt(getattr(start_row_cfg, "value", None))) if start_row_cfg else None
    cfg_end_dt = _cmp_dt(_parse_iso_dt(getattr(end_row_cfg, "value", None))) if end_row_cfg else None
    if not cfg_start_dt or not cfg_end_dt:
        return {"success": False, "error": "invalid config start_time/end_time", "data": {}}

    session = SessionLocal()
    tasks: List[Dict[str, Any]] = []
    task_specs: List[Dict[str, Any]] = []  # {task_id, executor_id, project_id, in_cfg_range}
    try:
        rows: List[ProjectTask] = (
            session.query(ProjectTask)
            .filter(
                ProjectTask.project_id == project_id,
                ProjectTask.scenario_field_config_id == DEFAULT_SCENARIO_FIELD_CONFIG_ID,
            )
            .order_by(ProjectTask.task_id)
            .all()
        )
        for r in rows:
            executor_id = str(r.executor_id or "").strip()
            task_id = str(r.task_id or "").strip()
            if not executor_id or not task_id:
                continue

            due_dt_a = _cmp_dt(r.due_date)
            in_range_a = bool(due_dt_a and start_dt <= due_dt_a <= end_dt)

            # A 表已经是最近一年落库；但仍做一次兜底过滤，保证窗口一致
            if not in_range_a:
                continue

            tasks.append({"id": r.task_id, "name": r.content, "executorId": r.executor_id})
            in_cfg_range = bool(due_dt_a and cfg_start_dt <= due_dt_a <= cfg_end_dt)
            task_specs.append(
                {
                    "task_id": task_id,
                    "executor_id": executor_id,
                    "project_id": str(r.project_id or project_id),
                    "in_cfg_range": in_cfg_range,
                }
            )
    finally:
        session.close()

    # 3) B 表：全量删除后重插（避免 overdue 残留）
    delete_session = SessionLocal()
    try:
        delete_session.query(ProjectTaskDetail).filter(ProjectTaskDetail.project_id == project_id).delete(
            synchronize_session=False
        )
        # 逾期明细：每次同步时按 project_id 全量覆盖
        delete_session.query(ProjectTaskOverdueDetail).filter(
            ProjectTaskOverdueDetail.project_id == project_id
        ).delete(synchronize_session=False)
        delete_session.commit()
    finally:
        delete_session.close()

    # 4) 3 线程并发轮循拉详情 + eligible 判断 + upsert B
    field_id = str(
        payload.get("workHourFieldId")
        or os.getenv("TB_TOOL_BT_WORKHOUR_FIELD_ID")
        or os.getenv("TB_TOOL_B1_WORKHOUR_FIELD_ID")
        or DEFAULT_WORKHOUR_FIELD_ID
    )

    token_result = get_valid_access_token(payload or {})
    if not token_result.get("ok"):
        return {"success": False, "error": token_result.get("error", "failed to fetch dingtalk token"), "data": {}}
    access_token = token_result.get("access_token")

    # 按你的要求固定 3 条线程轮循
    thread_count = 3

    def _extract_item(result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        ding = ((result.get("data") or {}).get("dingtalk")) or {}
        raw_result = ding.get("result")
        if isinstance(raw_result, list) and raw_result:
            first = raw_result[0]
            return first if isinstance(first, dict) else None
        if isinstance(raw_result, dict):
            return raw_result
        return None

    def _upsert_detail_one(
        one_session,
        *,
        user_id: str,
        task_id: str,
        project_id_val: str,
        item: Dict[str, Any],
        wh: Optional[float],
        is_overdue: bool,
    ) -> None:
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
        stmt = select(ProjectTaskDetail).where(
            ProjectTaskDetail.task_id == task_id,
            ProjectTaskDetail.query_user_id == user_id,
        )
        row = one_session.scalars(stmt).first()
        if row:
            row.project_id = project_id_val
            row.work_hour_field_id = field_id
            row.work_hour = wh
            row.custom_fields_json = cfs if cfs is not None else None
            row.raw_json = raw_blob
            row.parent_task_id = str(item.get("parentTaskId") or "") or None
            row.task_list_id = str(item.get("taskListId") or "") or None
            row.task_stage_id = str(item.get("taskStageId") or item.get("stageId") or "") or None
            row.unique_id = unique_id
            row.is_overdue = is_overdue
            row.fetched_at = now
        else:
            one_session.add(
                ProjectTaskDetail(
                    project_id=project_id_val,
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
                    is_overdue=is_overdue,
                    fetched_at=now,
                )
            )

    def _upsert_overdue_one(
        one_session,
        *,
        user_id: str,
        task_id: str,
        project_id_val: str,
        item: Dict[str, Any],
        wh: Optional[float],
    ) -> None:
        """把逾期明细单独落到 overdue 表。"""

        cfs = item.get("customFields") or item.get("customfields")
        try:
            raw_blob = json.dumps(item, ensure_ascii=False)
        except Exception:
            raw_blob = None

        now = datetime.now(timezone.utc)
        stmt = select(ProjectTaskOverdueDetail).where(
            ProjectTaskOverdueDetail.task_id == task_id,
            ProjectTaskOverdueDetail.query_user_id == user_id,
            ProjectTaskOverdueDetail.project_id == project_id_val,
        )
        row = one_session.scalars(stmt).first()
        if row:
            row.work_hour = wh
            row.custom_fields_json = cfs if cfs is not None else None
            row.raw_json = raw_blob
            row.fetched_at = now
        else:
            one_session.add(
                ProjectTaskOverdueDetail(
                    project_id=project_id_val,
                    task_id=task_id,
                    query_user_id=user_id,
                    work_hour=wh,
                    custom_fields_json=cfs if cfs is not None else None,
                    raw_json=raw_blob,
                    fetched_at=now,
                )
            )

    def _worker(task_specs_slice: List[Dict[str, Any]]) -> Dict[str, Any]:
        ok_upserts = 0
        skipped = 0
        fail_count = 0
        failures: List[Dict[str, Any]] = []

        # 每个 worker 线程单独 session，避免并发共享
        one_session = SessionLocal()
        try:
            for spec in task_specs_slice:
                q_payload: Dict[str, Any] = {
                    "userId": spec["executor_id"],
                    "taskId": spec["task_id"],
                    "projectId": spec["project_id"],
                    "force_refresh": True,
                    "access_token": access_token,
                    "workHourFieldId": field_id,
                }
                dres = query_user_tasks_service(q_payload)
                if not dres.get("success"):
                    fail_count += 1
                    failures.append(
                        {"taskId": spec["task_id"], "executorId": spec["executor_id"], "error": dres.get("error")}
                    )
                    continue

                item = _extract_item(dres)
                if not item:
                    fail_count += 1
                    failures.append(
                        {"taskId": spec["task_id"], "executorId": spec["executor_id"], "error": "empty dingtalk detail"}
                    )
                    continue

                tag_ids = item.get("tagIds") or item.get("tagids") or []
                is_overdue = False
                if isinstance(tag_ids, list):
                    for t in tag_ids:
                        if str(t) == OVERDUE_TAG_ID:
                            is_overdue = True
                            break

                wh = parse_workhour_from_task_dict(item, field_id)
                if bool(spec.get("in_cfg_range")):
                    _upsert_detail_one(
                        one_session,
                        user_id=spec["executor_id"],
                        task_id=spec["task_id"],
                        project_id_val=spec["project_id"],
                        item=item,
                        wh=wh,
                        is_overdue=is_overdue,
                    )
                else:
                    skipped += 1
                # 逾期明细独立落表：把 is_overdue 的明细拆出来
                # 由于统计时会按 project_tasks.due_date 再筛“季度窗口”，这里不做二次窗口过滤。
                if is_overdue:
                    _upsert_overdue_one(
                        one_session,
                        user_id=spec["executor_id"],
                        task_id=spec["task_id"],
                        project_id_val=spec["project_id"],
                        item=item,
                        wh=wh,
                    )
                one_session.commit()
                ok_upserts += 1
        finally:
            one_session.close()

        return {
            "ok_upserts": ok_upserts,
            "skipped": skipped,
            "fail_count": fail_count,
            "failures": failures,
        }

    specs_by_worker: List[List[Dict[str, str]]] = [[] for _ in range(thread_count)]
    for idx, spec in enumerate(task_specs):
        specs_by_worker[idx % thread_count].append(spec)

    b_upserts = 0
    b_skipped = 0
    b_fail = 0
    b_failures: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=thread_count) as pool:
        futures = [pool.submit(_worker, slice_specs) for slice_specs in specs_by_worker if slice_specs]
        for fut in futures:
            r = fut.result()
            b_upserts += int(r.get("ok_upserts", 0) or 0)
            b_skipped += int(r.get("skipped", 0) or 0)
            b_fail += int(r.get("fail_count", 0) or 0)
            b_failures.extend(r.get("failures") or [])

    return {
        "success": True,
        "data": {
            "sync": sync_out.get("data") or {},
            "tasks": tasks,
            "b_sync": {
                "window": {"start": start_iso, "end": end_iso},
                "task_count_in_a": len(task_specs),
                "b_upserts": b_upserts,
                "b_skipped": b_skipped,
                "b_fail": b_fail,
                "failures": b_failures[:20],
                "mode": "delete-reinsert",
            },
        },
    }


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
    tag_ids = item.get("tagIds") or item.get("tagids") or []
    is_overdue = False
    if isinstance(tag_ids, list):
        for t in tag_ids:
            if str(t) == OVERDUE_TAG_ID:
                is_overdue = True
                break
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
            row.is_overdue = is_overdue
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
                    is_overdue=is_overdue,
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


def sync_project_details_in_config_time_range_service(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    用 config.start_time/end_time 作为窗口：
    1) 先通过 query_project_tasks_service 拉列表（不落库）
    2) 按 scenario=软件开发 过滤后 upsert 到 A 表
    3) 仅同步窗口内任务的详情到 B 表（delete-reinsert）

    注意：该接口不负责更新 C 表（overdue），全量更新才会更新 C。
    """

    payload = dict(payload or {})
    user_id = str(payload.get("userId") or payload.get("userid") or "").strip()
    project_id = str(payload.get("projectId") or payload.get("projectid") or "").strip()
    if not user_id or not project_id:
        return {"success": False, "error": "missing userId or projectId", "data": {}}

    # 读取 config.start/end 作为查询窗口
    session = SessionLocal()
    try:
        start_row = session.query(DbConfig).filter(DbConfig.type_ == "start_time").first()
        end_row = session.query(DbConfig).filter(DbConfig.type_ == "end_time").first()
        if not start_row or not end_row:
            return {"success": False, "error": "missing config start_time/end_time", "data": {}}
        start_dt = _parse_iso_dt(getattr(start_row, "value", None))
        end_dt = _parse_iso_dt(getattr(end_row, "value", None))
    finally:
        session.close()

    if not start_dt or not end_dt:
        return {"success": False, "error": "invalid config start_time/end_time", "data": {}}

    def _format_dt_for_tql(dt: datetime) -> str:
        d = dt.astimezone(timezone.utc).replace(microsecond=0)
        return d.strftime("%Y-%m-%dT%H:%M:%S") + ".000Z"

    query = "(dueDate >= '{start}') AND (dueDate <= '{end}')".format(
        start=_format_dt_for_tql(start_dt),
        end=_format_dt_for_tql(end_dt),
    )

    max_results = int(payload.get("maxResults", 500) or 500)
    max_pages = int(payload.get("maxPages", 200) or 200)

    list_payload = dict(payload)
    list_payload["userId"] = user_id
    list_payload["projectId"] = project_id
    list_payload["query"] = query
    list_payload["maxResults"] = max_results
    list_payload["maxPages"] = max_pages
    list_payload["force_refresh"] = True

    query_res = query_project_tasks_service(list_payload)
    if not query_res.get("success"):
        return {"success": False, "error": query_res.get("error", "query project tasks failed"), "data": query_res}

    # A 表落库（软件开发过滤）
    sync_out = sync_project_tasks_to_db(list_payload, query_result=query_res)
    if not sync_out.get("success"):
        return {"success": False, "error": sync_out.get("error", "sync project tasks failed"), "data": sync_out}

    # 从 A 表取窗口内任务，同步到 B 表（仅窗口内）
    # 删除旧 B（按 project_id 全量覆盖，保持口径稳定）
    del_sess = SessionLocal()
    try:
        del_sess.query(ProjectTaskDetail).filter(ProjectTaskDetail.project_id == project_id).delete(
            synchronize_session=False
        )
        del_sess.commit()
    finally:
        del_sess.close()

    token_result = get_valid_access_token(payload or {})
    if not token_result.get("ok"):
        return {"success": False, "error": token_result.get("error", "failed to fetch dingtalk token"), "data": {}}
    access_token = token_result.get("access_token")

    field_id = str(
        payload.get("workHourFieldId")
        or os.getenv("TB_TOOL_BT_WORKHOUR_FIELD_ID")
        or os.getenv("TB_TOOL_B1_WORKHOUR_FIELD_ID")
        or DEFAULT_WORKHOUR_FIELD_ID
    )

    session = SessionLocal()
    task_specs: List[Dict[str, str]] = []
    try:
        rows = (
            session.query(ProjectTask)
            .filter(ProjectTask.project_id == project_id)
            .filter(ProjectTask.scenario_field_config_id == DEFAULT_SCENARIO_FIELD_CONFIG_ID)
            .filter(ProjectTask.due_date != None)  # noqa: E711
            .filter(ProjectTask.due_date >= start_dt)
            .filter(ProjectTask.due_date <= end_dt)
            .order_by(ProjectTask.task_id)
            .all()
        )
        for r in rows:
            executor_id = str(getattr(r, "executor_id", "") or "").strip()
            task_id = str(getattr(r, "task_id", "") or "").strip()
            if not executor_id or not task_id:
                continue
            task_specs.append({"task_id": task_id, "executor_id": executor_id, "project_id": project_id})
    finally:
        session.close()

    def _extract_item(result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        ding = ((result.get("data") or {}).get("dingtalk")) or {}
        raw_result = ding.get("result")
        if isinstance(raw_result, list) and raw_result:
            first = raw_result[0]
            return first if isinstance(first, dict) else None
        if isinstance(raw_result, dict):
            return raw_result
        return None

    def _worker(task_specs_slice: List[Dict[str, str]]) -> Dict[str, Any]:
        ok_upserts = 0
        fail_count = 0
        failures: List[Dict[str, Any]] = []
        one_session = SessionLocal()
        try:
            for spec in task_specs_slice:
                q_payload: Dict[str, Any] = {
                    "userId": spec["executor_id"],
                    "taskId": spec["task_id"],
                    "projectId": spec["project_id"],
                    "force_refresh": True,
                    "access_token": access_token,
                    "workHourFieldId": field_id,
                }
                dres = query_user_tasks_service(q_payload)
                if not dres.get("success"):
                    fail_count += 1
                    failures.append(
                        {"taskId": spec["task_id"], "executorId": spec["executor_id"], "error": dres.get("error")}
                    )
                    continue

                item = _extract_item(dres)
                if not item:
                    fail_count += 1
                    failures.append(
                        {"taskId": spec["task_id"], "executorId": spec["executor_id"], "error": "empty dingtalk detail"}
                    )
                    continue

                tag_ids = item.get("tagIds") or item.get("tagids") or []
                is_overdue = False
                if isinstance(tag_ids, list):
                    for t in tag_ids:
                        if str(t) == OVERDUE_TAG_ID:
                            is_overdue = True
                            break

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
                stmt = select(ProjectTaskDetail).where(
                    ProjectTaskDetail.task_id == spec["task_id"],
                    ProjectTaskDetail.query_user_id == spec["executor_id"],
                )
                row = one_session.scalars(stmt).first()
                if row:
                    row.project_id = spec["project_id"]
                    row.work_hour_field_id = field_id
                    row.work_hour = wh
                    row.custom_fields_json = cfs if cfs is not None else None
                    row.raw_json = raw_blob
                    row.parent_task_id = str(item.get("parentTaskId") or "") or None
                    row.task_list_id = str(item.get("taskListId") or "") or None
                    row.task_stage_id = str(item.get("taskStageId") or item.get("stageId") or "") or None
                    row.unique_id = unique_id
                    row.is_overdue = is_overdue
                    row.fetched_at = now
                else:
                    one_session.add(
                        ProjectTaskDetail(
                            project_id=spec["project_id"],
                            task_id=spec["task_id"],
                            query_user_id=spec["executor_id"],
                            work_hour_field_id=field_id,
                            work_hour=wh,
                            custom_fields_json=cfs if cfs is not None else None,
                            raw_json=raw_blob,
                            parent_task_id=str(item.get("parentTaskId") or "") or None,
                            task_list_id=str(item.get("taskListId") or "") or None,
                            task_stage_id=str(item.get("taskStageId") or item.get("stageId") or "") or None,
                            unique_id=unique_id,
                            is_overdue=is_overdue,
                            fetched_at=now,
                        )
                    )
                one_session.commit()
                ok_upserts += 1
        finally:
            one_session.close()

        return {"ok_upserts": ok_upserts, "fail_count": fail_count, "failures": failures}

    thread_count = 3
    specs_by_worker: List[List[Dict[str, str]]] = [[] for _ in range(thread_count)]
    for idx, spec in enumerate(task_specs):
        specs_by_worker[idx % thread_count].append(spec)

    b_upserts = 0
    b_fail = 0
    b_failures: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=thread_count) as pool:
        futures = [pool.submit(_worker, slice_specs) for slice_specs in specs_by_worker if slice_specs]
        for fut in futures:
            r = fut.result()
            b_upserts += int(r.get("ok_upserts", 0) or 0)
            b_fail += int(r.get("fail_count", 0) or 0)
            b_failures.extend(r.get("failures") or [])

    return {
        "success": True,
        "data": {
            "query": query,
            "a_sync": sync_out.get("data") or {},
            "b_sync": {
                "task_count_in_a": len(task_specs),
                "b_upserts": b_upserts,
                "b_fail": b_fail,
                "failures": b_failures[:20],
                "mode": "delete-reinsert",
            },
        },
    }
