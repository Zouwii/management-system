"""
现场问题跟踪 — A/B 表同步逻辑.

A 表: onsite_problem_tasks (列表快照)
B 表: onsite_problem_details (明细, 解析 customField)
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select

from base.db.engine import OnsiteSessionLocal
from base.db.orm import OnsiteProblemDetail, OnsiteProblemTask
from base.projects.task_service import query_project_tasks_service, query_user_tasks_service

# ── 项目常量 ─────────────────────────────────────────────────
ONSITE_PROJECT_ID = "616e6868a46ec51df166f4cd"
ONSITE_SCENARIO_FIELD_CONFIG_ID = "616e686948312307a5a9f994"

# ── customField ID 常量 ──────────────────────────────────────
CF_VEHICLE_MODEL            = "659369d32ae435dd0b3c803e"  # 车型 (cascading)
CF_CARRIER_TYPE             = "637c2e2ffbb56c003fdd74e9"  # 载具配置 (dropDown)
CF_OCCURRENCE_FREQUENCY     = "62c51d82d7ab965fbdebd686"  # 复现概率 (dropDown)
CF_SOFTWARE_VERSION         = "6645bd4d22e1f70dadb953f6"  # JZTOTAL包版本 (dropDown)
CF_PROBLEM_DESCRIPTION      = "624e4bf0972b3d03d3008c4c"  # 问题描述 (text)
CF_INVESTIGATION_CONCLUSION = "69241440caabefe748f91359"  # 排查结论 (rtf)
CF_DOC_VALUE                = "692414313ffb7e9afc4e9f43"  # 排查文档价值 (dropDown)
CF_INVESTIGATION_DOC        = "6924139133e26574155ea68b"  # 排查文档 (lookup2)
CF_ATTACHMENTS              = "625f75e9882430143f5bfd0a"  # 其他附件信息 (work)
CF_PROBLEM_CATEGORY         = "691a95544ce9d3d5a5e541e1"  # 问题类型分类 (cascading)
CF_PROBLEM_MODULE           = "691a95f304c9e52bc9058bd6"  # 问题模块分类 (dropDown)
CF_GUIDE_DOC                = "62651eadef4cf6063244aa5c"  # 指导文档 (lookup)
CF_FORMAL_VERSION           = "625f8339882430143f5c0b9a"  # 正式版本 (text)
CF_ROOT_CAUSE               = "625f8317d472ef3d5c2f39a4"  # 原因分析 (text)
CF_SOLUTION                 = "625f8329b416f5118bb099b2"  # 解决方案 (text)
CF_SUBMITTER                = "68f637359ae2d0854e946cb3"  # 提交者 (text)


# ── helpers ──────────────────────────────────────────────────

def _parse_iso_dt(value: Any) -> Optional[datetime]:
    if not value:
        return None
    t = str(value).strip()
    if not t:
        return None
    if t.endswith("Z"):
        t = t[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(t)
    except ValueError:
        return None


def _extract_custom_field_title(item: Dict[str, Any], cfid: str) -> Optional[str]:
    """从 customFields 中按 cfId 取第一个 value 的 title."""
    cfs = item.get("customFields") or item.get("customfields") or []
    if not isinstance(cfs, list):
        return None
    for cf in cfs:
        if not isinstance(cf, dict):
            continue
        if str(cf.get("customFieldId") or cf.get("customfieldId") or "") != cfid:
            continue
        values = cf.get("value") or []
        if isinstance(values, list) and values:
            first = values[0]
            if isinstance(first, dict):
                return str(first.get("title") or "").strip() or None
            return str(first).strip() or None
    return None


def _extract_attachment_titles(item: Dict[str, Any], cfid: str) -> Optional[str]:
    """从 customFields 的 work 类型中提取所有附件文件名，用分号拼接."""
    cfs = item.get("customFields") or item.get("customfields") or []
    if not isinstance(cfs, list):
        return None
    for cf in cfs:
        if not isinstance(cf, dict):
            continue
        if str(cf.get("customFieldId") or cf.get("customfieldId") or "") != cfid:
            continue
        values = cf.get("value") or []
        if isinstance(values, list) and values:
            titles = []
            for v in values:
                if isinstance(v, dict):
                    t = str(v.get("title") or "").strip()
                    if t:
                        titles.append(t)
            return "; ".join(titles) if titles else None
    return None


def _str_list(lst: Any) -> Optional[List[str]]:
    if not isinstance(lst, list):
        return None
    return [str(x) for x in lst if x is not None]


# ── A 表写入 ─────────────────────────────────────────────────

def _apply_task_dict_to_onsite_a(obj: OnsiteProblemTask, d: Dict[str, Any], synced_at: datetime) -> None:
    obj.task_id = str(d.get("taskId") or "")
    obj.project_id = str(d.get("projectId") or "")
    obj.content = str(d.get("content") or "")
    obj.scenario_field_config_id = str(d.get("scenariofieldconfigId") or d.get("scenarioFieldConfigId") or "")
    obj.stage_id = str(d.get("stageId") or "")
    obj.task_list_id = str(d.get("taskListId") or "")
    obj.task_stage_id = str(d.get("taskStageId") or "")
    obj.taskflow_status_id = str(d.get("taskflowstatusId") or d.get("taskflowStatusId") or "")
    obj.executor_id = str(d.get("executorId") or "")
    obj.creator_id = str(d.get("creatorId") or "")
    obj.due_date = _parse_iso_dt(d.get("dueDate"))
    obj.start_date = _parse_iso_dt(d.get("startDate"))
    obj.ding_created = _parse_iso_dt(d.get("created"))
    obj.ding_updated = _parse_iso_dt(d.get("updated"))
    obj.note = str(d.get("note") or "")
    obj.priority = int(d.get("priority") or 0)
    obj.progress = int(d.get("progress") or 0)
    obj.visible = str(d.get("visible") or "members")
    obj.is_archived = bool(d.get("isArchived"))
    obj.is_deleted = bool(d.get("isDeleted"))
    obj.is_done = bool(d.get("isDone"))
    obj.ancestor_ids = _str_list(d.get("ancestorIds"))
    obj.involve_members = _str_list(d.get("involveMembers"))
    obj.tag_ids = _str_list(d.get("tagIds"))
    obj.labels = d.get("labels") if isinstance(d.get("labels"), list) else None
    # customfield_ids: 只存 id 列表
    cfs = d.get("customfields") or d.get("customFields") or []
    obj.customfield_ids = [str(cf.get("customfieldId") or cf.get("customFieldId") or "")
                           for cf in cfs if isinstance(cf, dict)
                           and (cf.get("customfieldId") or cf.get("customFieldId"))] or None
    try:
        obj.raw_json = json.dumps(d, ensure_ascii=False)
    except Exception:
        obj.raw_json = None
    obj.list_synced_at = synced_at


def sync_onsite_a_table(payload: Dict[str, Any],
                        query_result: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    拉项目任务列表并 upsert A 表 onsite_problem_tasks.

    若传入 query_result (已调用的 query_project_tasks_service 返回值), 则不再请求.
    """
    payload = dict(payload or {})
    user_id = str(payload.get("userId") or payload.get("userid") or "").strip()

    if query_result is None:
        qp = {
            "userId": user_id,
            "projectId": ONSITE_PROJECT_ID,
            "maxResults": 100,
            "maxPages": payload.get("maxPages", 20),
            "force_refresh": bool(payload.get("force_refresh")),
        }
        query_result = query_project_tasks_service(qp)
        if not query_result.get("success"):
            return {
                "success": False,
                "error": query_result.get("error", "dingtalk query failed"),
                "data": query_result,
            }

    ding = (query_result.get("data") or {}).get("dingtalk") or {}
    all_rows = ding.get("result") if isinstance(ding.get("result"), list) else []

    now = datetime.now(timezone.utc)
    session = OnsiteSessionLocal()
    upserted = 0
    try:
        for d in all_rows:
            if not isinstance(d, dict):
                continue
            pid = str(d.get("projectId") or "")
            tid = str(d.get("taskId") or "")
            if not pid or not tid:
                continue
            stmt = select(OnsiteProblemTask).where(
                OnsiteProblemTask.project_id == pid,
                OnsiteProblemTask.task_id == tid,
            )
            existing = session.scalars(stmt).first()
            if existing:
                _apply_task_dict_to_onsite_a(existing, d, now)
            else:
                row = OnsiteProblemTask()
                _apply_task_dict_to_onsite_a(row, d, now)
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
            "fetched_count": len(all_rows),
            "synced_at": now.isoformat(),
        },
    }


# ── B 表写入 ─────────────────────────────────────────────────

def _extract_detail_item(dres: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    ding = ((dres.get("data") or {}).get("dingtalk")) or {}
    raw = ding.get("result")
    if isinstance(raw, list) and raw:
        return raw[0] if isinstance(raw[0], dict) else None
    if isinstance(raw, dict):
        return raw
    return None


def sync_onsite_b_table_from_a(user_id: str) -> Dict[str, Any]:
    """
    从 A 表读取所有 task, 逐个调用详情 API, 解析 customField, upsert B 表.
    """
    user_id = str(user_id).strip()
    if not user_id:
        return {"success": False, "error": "missing userId", "data": {}}

    a_session = OnsiteSessionLocal()
    try:
        tasks = (
            a_session.query(OnsiteProblemTask)
            .filter(OnsiteProblemTask.project_id == ONSITE_PROJECT_ID)
            .all()
        )
        task_specs: List[Dict[str, str]] = []
        for t in tasks:
            ex_id = (getattr(t, "executor_id", "") or "").strip()
            tid = (getattr(t, "task_id", "") or "").strip()
            if not ex_id or not tid:
                continue
            task_specs.append({"task_id": tid, "executor_id": ex_id})
    finally:
        a_session.close()

    if not task_specs:
        return {"success": True, "data": {"task_count": 0, "upserted": 0, "failed": 0}}

    b_session = OnsiteSessionLocal()
    upserted = 0
    failed = 0
    failures: List[Dict[str, Any]] = []
    pending_commit = 0
    batch_size = 20

    try:
        for spec in task_specs:
            tid = spec["task_id"]
            ex_id = spec["executor_id"]

            # 每次用自己的 executorId 调详情 API
            dres = query_user_tasks_service({
                "userId": ex_id,
                "taskId": tid,
                "force_refresh": True,
            })
            if not dres.get("success"):
                failed += 1
                failures.append({"taskId": tid, "executorId": ex_id, "error": dres.get("error")})
                continue

            item = _extract_detail_item(dres)
            if not item:
                failed += 1
                failures.append({"taskId": tid, "executorId": ex_id, "error": "empty detail"})
                continue

            # 解析全部 customField
            vehicle_model = _extract_custom_field_title(item, CF_VEHICLE_MODEL)
            carrier_type = _extract_custom_field_title(item, CF_CARRIER_TYPE)
            occurrence_frequency = _extract_custom_field_title(item, CF_OCCURRENCE_FREQUENCY)
            software_version = _extract_custom_field_title(item, CF_SOFTWARE_VERSION)
            problem_description = _extract_custom_field_title(item, CF_PROBLEM_DESCRIPTION)
            investigation_conclusion = _extract_custom_field_title(item, CF_INVESTIGATION_CONCLUSION)
            doc_value = _extract_custom_field_title(item, CF_DOC_VALUE)
            investigation_doc = _extract_custom_field_title(item, CF_INVESTIGATION_DOC)
            attachments = _extract_attachment_titles(item, CF_ATTACHMENTS)
            problem_category = _extract_custom_field_title(item, CF_PROBLEM_CATEGORY)
            problem_module = _extract_custom_field_title(item, CF_PROBLEM_MODULE)
            guide_doc = _extract_custom_field_title(item, CF_GUIDE_DOC)
            formal_version = _extract_custom_field_title(item, CF_FORMAL_VERSION)
            root_cause = _extract_custom_field_title(item, CF_ROOT_CAUSE)
            solution = _extract_custom_field_title(item, CF_SOLUTION)
            submitter = _extract_custom_field_title(item, CF_SUBMITTER)

            cfs = item.get("customFields") or item.get("customfields")
            try:
                raw_blob = json.dumps(item, ensure_ascii=False)
            except Exception:
                raw_blob = None

            now = datetime.now(timezone.utc)

            stmt = select(OnsiteProblemDetail).where(
                OnsiteProblemDetail.task_id == tid,
                OnsiteProblemDetail.query_user_id == ex_id,
            )
            row = b_session.scalars(stmt).first()
            if row:
                row.project_id = str(item.get("projectId") or "")
                row.unique_id = int(item.get("uniqueId")) if item.get("uniqueId") is not None else None
                row.content = str(item.get("content") or "")
                row.executor_id = str(item.get("executorId") or "")
                row.creator_id = str(item.get("creatorId") or "")
                row.scenario_field_config_id = str(item.get("scenarioFieldConfigId") or item.get("scenariofieldconfigId") or "")
                row.taskflow_status_id = str(item.get("taskflowStatusId") or item.get("taskflowstatusId") or "")
                row.task_list_id = str(item.get("taskListId") or "")
                row.task_stage_id = str(item.get("taskStageId") or "")
                row.due_date = _parse_iso_dt(item.get("dueDate"))
                row.start_date = _parse_iso_dt(item.get("startDate"))
                row.is_done = bool(item.get("isDone"))
                row.is_archived = bool(item.get("isArchived"))
                row.priority = int(item.get("priority") or 0)
                row.progress = int(item.get("progress") or 0)
                row.note = str(item.get("note") or "")
                row.visible = str(item.get("visible") or "")
                row.tag_ids = _str_list(item.get("tagIds"))
                row.involve_members = _str_list(item.get("involveMembers"))
                row.ancestor_ids = _str_list(item.get("ancestorIds"))
                row.labels = item.get("labels") if isinstance(item.get("labels"), list) else None
                # 拆列
                row.vehicle_model = vehicle_model
                row.carrier_type = carrier_type
                row.occurrence_frequency = occurrence_frequency
                row.software_version = software_version
                row.problem_description = problem_description
                row.investigation_conclusion = investigation_conclusion
                row.doc_value = doc_value
                row.investigation_doc = investigation_doc
                row.attachments = attachments
                row.problem_category = problem_category
                row.problem_module = problem_module
                row.guide_doc = guide_doc
                row.formal_version = formal_version
                row.root_cause = root_cause
                row.solution = solution
                row.submitter = submitter
                row.custom_fields_json = cfs
                row.raw_json = raw_blob
                row.fetched_at = now
            else:
                b_session.add(OnsiteProblemDetail(
                    project_id=str(item.get("projectId") or ""),
                    task_id=tid,
                    query_user_id=ex_id,
                    unique_id=int(item.get("uniqueId")) if item.get("uniqueId") is not None else None,
                    content=str(item.get("content") or ""),
                    executor_id=str(item.get("executorId") or ""),
                    creator_id=str(item.get("creatorId") or ""),
                    scenario_field_config_id=str(item.get("scenarioFieldConfigId") or item.get("scenariofieldconfigId") or ""),
                    taskflow_status_id=str(item.get("taskflowStatusId") or item.get("taskflowstatusId") or ""),
                    task_list_id=str(item.get("taskListId") or ""),
                    task_stage_id=str(item.get("taskStageId") or ""),
                    due_date=_parse_iso_dt(item.get("dueDate")),
                    start_date=_parse_iso_dt(item.get("startDate")),
                    is_done=bool(item.get("isDone")),
                    is_archived=bool(item.get("isArchived")),
                    priority=int(item.get("priority") or 0),
                    progress=int(item.get("progress") or 0),
                    note=str(item.get("note") or ""),
                    visible=str(item.get("visible") or ""),
                    tag_ids=_str_list(item.get("tagIds")),
                    involve_members=_str_list(item.get("involveMembers")),
                    ancestor_ids=_str_list(item.get("ancestorIds")),
                    labels=item.get("labels") if isinstance(item.get("labels"), list) else None,
                    # 拆列
                    vehicle_model=vehicle_model,
                    carrier_type=carrier_type,
                    occurrence_frequency=occurrence_frequency,
                    software_version=software_version,
                    problem_description=problem_description,
                    investigation_conclusion=investigation_conclusion,
                    doc_value=doc_value,
                    investigation_doc=investigation_doc,
                    attachments=attachments,
                    problem_category=problem_category,
                    problem_module=problem_module,
                    guide_doc=guide_doc,
                    formal_version=formal_version,
                    root_cause=root_cause,
                    solution=solution,
                    submitter=submitter,
                    custom_fields_json=cfs,
                    raw_json=raw_blob,
                    fetched_at=now,
                ))

            pending_commit += 1
            if pending_commit >= batch_size:
                b_session.commit()
                pending_commit = 0
            upserted += 1

        if pending_commit > 0:
            b_session.commit()
    except Exception as e:
        b_session.rollback()
        return {"success": False, "error": str(e), "data": {}}
    finally:
        b_session.close()

    return {
        "success": True,
        "data": {
            "task_count": len(task_specs),
            "upserted": upserted,
            "failed": failed,
            "failures": failures[:20],
        },
    }


# ── 全量同步入口 ──────────────────────────────────────────────

def sync_onsite_full(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    全量同步：拉列表 → 写 A 表 → 写 B 表.
    POST 传入: { userId }
    """
    payload = dict(payload or {})
    user_id = str(payload.get("userId") or payload.get("userid") or "").strip()
    if not user_id:
        return {"success": False, "error": "missing userId", "data": {}}

    # Step 1: 拉列表 → 写 A 表
    a_res = sync_onsite_a_table({"userId": user_id, "force_refresh": True})
    if not a_res.get("success"):
        return {"success": False, "error": a_res.get("error", "A table sync failed"), "data": a_res}

    # Step 2: 从 A 表读任务 → 写 B 表
    b_res = sync_onsite_b_table_from_a(user_id)

    return {
        "success": a_res.get("success"),
        "data": {
            "a_sync": a_res.get("data") or {},
            "b_sync": b_res.get("data") or {},
        },
    }
