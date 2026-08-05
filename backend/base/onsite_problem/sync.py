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

from base.db.engine import OnsiteSessionLocal, SessionLocal
from base.db.orm import Config as DbConfig, OnsiteProblemDetail, OnsiteProblemTask
from base.projects.task_service import query_project_tasks_service, query_user_tasks_service

# ── A 表游标持久化（断点续拉）─────────────────────────────────
_CURSOR_CONFIG_TYPE = "onsite_a_cursor"


def _get_onsite_a_cursor() -> Optional[str]:
    """读取上次 A 表同步的 nextToken 游标；无则返回 None."""
    session = SessionLocal()
    try:
        row = session.query(DbConfig).filter(DbConfig.type_ == _CURSOR_CONFIG_TYPE).first()
        if not row:
            return None
        val = (row.value or "").strip()
        return val if val else None
    finally:
        session.close()


def _set_onsite_a_cursor(next_token: Optional[str]) -> None:
    """写入/清除 A 表同步游标."""
    session = SessionLocal()
    try:
        row = session.query(DbConfig).filter(DbConfig.type_ == _CURSOR_CONFIG_TYPE).first()
        nt = (next_token or "").strip()
        if row:
            if nt:
                row.value = nt
            else:
                session.delete(row)
        else:
            if nt:
                session.add(DbConfig(type_=_CURSOR_CONFIG_TYPE, value=nt))
        session.commit()
    except Exception:
        session.rollback()
    finally:
        session.close()


def reset_onsite_a_cursor() -> Dict[str, Any]:
    """清空 A 表游标，下次同步从头开始."""
    cursor_before = _get_onsite_a_cursor()
    _set_onsite_a_cursor(None)
    return {
        "success": True,
        "data": {
            "was_active": cursor_before is not None,
            "cleared": True,
        },
    }


def get_onsite_a_cursor_status() -> Dict[str, Any]:
    """查询当前 A 表游标状态."""
    cursor = _get_onsite_a_cursor()
    return {
        "success": True,
        "data": {
            "active": cursor is not None,
            "next_token": cursor,
        },
    }

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
        if str(cf.get("customFieldId") or cf.get("customfieldId") or cf.get("cfId") or "") != cfid:
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
        if str(cf.get("customFieldId") or cf.get("customfieldId") or cf.get("cfId") or "") != cfid:
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

    断点续拉：若 Config 表存有上次同步的 nextToken 游标，则接着上次的位置翻页；
    拉完全量后自动清除游标；force_refresh=True 时忽略游标从头拉.

    若传入 query_result (已调用的 query_project_tasks_service 返回值), 则不再请求.
    """
    payload = dict(payload or {})
    user_id = str(payload.get("userId") or payload.get("userid") or "").strip()
    force_refresh = bool(payload.get("force_refresh"))

    # ── 读游标 ──
    saved_cursor = None if force_refresh else _get_onsite_a_cursor()

    if query_result is None:
        qp = {
            "userId": user_id,
            "projectId": ONSITE_PROJECT_ID,
            "maxResults": 100,
            "maxPages": 100,
            "force_refresh": force_refresh or (saved_cursor is None),
        }
        if saved_cursor:
            qp["nextToken"] = saved_cursor
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

    # ── 存游标 ──
    next_token = ding.get("nextToken")
    _set_onsite_a_cursor(next_token)

    return {
        "success": True,
        "data": {
            "upserted": upserted,
            "fetched_count": len(all_rows),
            "synced_at": now.isoformat(),
            "cursor": {
                "continued_from": saved_cursor is not None,
                "has_more": bool(next_token),
                "next_token": next_token if next_token else None,
            },
        },
    }


# ── B 表同步（TB Open API via proxy，含评论+附件）───────────────

def _upsert_detail_row(sess, task: Dict[str, Any], tid: str, user_id: str,
                       comments_json, attachments_json, source_task: Optional[OnsiteProblemTask] = None):
    """单条 B 表 upsert 逻辑，供单线程和多线程共用."""
    from base.db.orm import OnsiteProblemDetail

    vehicle_model = _extract_custom_field_title(task, CF_VEHICLE_MODEL)
    carrier_type = _extract_custom_field_title(task, CF_CARRIER_TYPE)
    occurrence_frequency = _extract_custom_field_title(task, CF_OCCURRENCE_FREQUENCY)
    software_version = _extract_custom_field_title(task, CF_SOFTWARE_VERSION)
    problem_description = _extract_custom_field_title(task, CF_PROBLEM_DESCRIPTION)
    investigation_conclusion = _extract_custom_field_title(task, CF_INVESTIGATION_CONCLUSION)
    doc_value = _extract_custom_field_title(task, CF_DOC_VALUE)
    investigation_doc = _extract_custom_field_title(task, CF_INVESTIGATION_DOC)
    attachments_text = _extract_attachment_titles(task, CF_ATTACHMENTS)
    problem_category = _extract_custom_field_title(task, CF_PROBLEM_CATEGORY)
    problem_module = _extract_custom_field_title(task, CF_PROBLEM_MODULE)
    guide_doc = _extract_custom_field_title(task, CF_GUIDE_DOC)
    formal_version = _extract_custom_field_title(task, CF_FORMAL_VERSION)
    root_cause = _extract_custom_field_title(task, CF_ROOT_CAUSE)
    solution = _extract_custom_field_title(task, CF_SOLUTION)
    submitter = _extract_custom_field_title(task, CF_SUBMITTER)
    cfs = task.get("customfields") or task.get("customFields")
    try:
        raw_blob = json.dumps(task, ensure_ascii=False)
    except Exception:
        raw_blob = None

    now = datetime.now(timezone.utc)
    # 创建/更新时间以 A 表列表接口落库的值为准；API 详情作为兼容回退。
    ding_created = (source_task.ding_created if source_task else None) or _parse_iso_dt(task.get("created"))
    ding_updated = (source_task.ding_updated if source_task else None) or _parse_iso_dt(task.get("updated"))
    stmt = select(OnsiteProblemDetail).where(OnsiteProblemDetail.task_id == tid)
    row = sess.scalars(stmt).first()
    if row:
        row.content = str(task.get("content") or "")
        row.executor_id = str(task.get("executorId") or "")
        row.creator_id = str(task.get("creatorId") or "")
        row.scenario_field_config_id = str(task.get("scenarioFieldConfigId") or task.get("scenariofieldconfigId") or "")
        row.due_date = _parse_iso_dt(task.get("dueDate"))
        row.start_date = _parse_iso_dt(task.get("startDate"))
        row.ding_created = ding_created
        row.ding_updated = ding_updated
        row.is_done = bool(task.get("isDone"))
        row.is_archived = bool(task.get("isArchived"))
        row.priority = int(task.get("priority") or 0)
        row.progress = int(task.get("progress") or 0)
        row.note = str(task.get("note") or "")
        row.vehicle_model = vehicle_model
        row.carrier_type = carrier_type
        row.occurrence_frequency = occurrence_frequency
        row.software_version = software_version
        row.problem_description = problem_description
        row.investigation_conclusion = investigation_conclusion
        row.doc_value = doc_value
        row.investigation_doc = investigation_doc
        row.attachments = attachments_text
        row.problem_category = problem_category
        row.problem_module = problem_module
        row.guide_doc = guide_doc
        row.formal_version = formal_version
        row.root_cause = root_cause
        row.solution = solution
        row.submitter = submitter
        row.custom_fields_json = cfs
        row.raw_json = raw_blob
        row.comments_json = comments_json
        row.attachments_json = attachments_json
        row.fetched_at = now
    else:
        sess.add(OnsiteProblemDetail(
            project_id=str(task.get("projectId") or ONSITE_PROJECT_ID),
            task_id=tid,
            query_user_id=user_id,
            content=str(task.get("content") or ""),
            executor_id=str(task.get("executorId") or ""),
            creator_id=str(task.get("creatorId") or ""),
            scenario_field_config_id=str(task.get("scenarioFieldConfigId") or task.get("scenariofieldconfigId") or ""),
            due_date=_parse_iso_dt(task.get("dueDate")),
            start_date=_parse_iso_dt(task.get("startDate")),
            ding_created=ding_created,
            ding_updated=ding_updated,
            is_done=bool(task.get("isDone")),
            is_archived=bool(task.get("isArchived")),
            priority=int(task.get("priority") or 0),
            progress=int(task.get("progress") or 0),
            note=str(task.get("note") or ""),
            vehicle_model=vehicle_model,
            carrier_type=carrier_type,
            occurrence_frequency=occurrence_frequency,
            software_version=software_version,
            problem_description=problem_description,
            investigation_conclusion=investigation_conclusion,
            doc_value=doc_value,
            investigation_doc=investigation_doc,
            attachments=attachments_text,
            problem_category=problem_category,
            problem_module=problem_module,
            guide_doc=guide_doc,
            formal_version=formal_version,
            root_cause=root_cause,
            solution=solution,
            submitter=submitter,
            custom_fields_json=cfs,
            raw_json=raw_blob,
            comments_json=comments_json,
            attachments_json=attachments_json,
            fetched_at=now,
        ))


def _b_worker(task_ids: List[str], user_id: str) -> Dict[str, Any]:
    """单个线程的 B 表同步 worker：拉代理 API + upsert DB."""
    from base.onsite_problem.tb_proxy import fetch_task_with_comments

    upserted = 0
    failed = 0
    errors: List[Dict[str, Any]] = []
    sess = OnsiteSessionLocal()
    a_session = OnsiteSessionLocal()
    pending = 0
    try:
        source_tasks = {
            row.task_id: row
            for row in a_session.query(OnsiteProblemTask).filter(OnsiteProblemTask.task_id.in_(task_ids)).all()
        }
        for tid in task_ids:
            try:
                result = fetch_task_with_comments(tid)
            except Exception as e:
                failed += 1
                errors.append({"task_id": tid, "error": str(e)})
                continue

            _upsert_detail_row(
                sess, result["task"], tid, user_id,
                result["comments_json"], result["attachments_json"],
                source_task=source_tasks.get(tid),
            )
            pending += 1
            upserted += 1
            if pending >= 10:
                sess.commit()
                pending = 0
        if pending > 0:
            sess.commit()
    except Exception as e:
        sess.rollback()
        errors.append({"error": str(e)})
    finally:
        sess.close()
        a_session.close()
    return {"upserted": upserted, "failed": failed, "errors": errors}


def sync_onsite_b_table_via_proxy(user_id: str,
                                  thread_count: int = 5,
                                  skip_existing: bool = False) -> Dict[str, Any]:
    """
    从 A 表读取所有 task, 经 TB Open API via proxy 拉详情 + 评论 + 附件,
    多线程 upsert B 表 onsite_problem_details（含 comments_json + attachments_json）.

    Args:
        user_id: 用户 ID
        thread_count: 并行线程数，默认 5
        skip_existing: True 时跳过 B 表已有记录的 task
    """
    user_id = str(user_id).strip()
    if not user_id:
        return {"success": False, "error": "missing userId", "data": {}}

    from base.onsite_problem.tb_proxy import check_proxy_health

    # ── 预检：代理凭据是否有效 ──
    proxy_ok, proxy_msg = check_proxy_health()
    if not proxy_ok:
        return {"success": False, "error": f"TB 代理凭据无效: {proxy_msg}", "data": {}}

    a_session = OnsiteSessionLocal()
    try:
        tasks = (
            a_session.query(OnsiteProblemTask)
            .filter(OnsiteProblemTask.project_id == ONSITE_PROJECT_ID)
            .all()
        )
        all_task_ids = [t.task_id for t in tasks if t.task_id]
    finally:
        a_session.close()

    if not all_task_ids:
        return {"success": True, "data": {"task_count": 0, "upserted": 0, "failed": 0}}

    # ── skip_existing: 跳过 B 表已有的 task ──
    if skip_existing:
        b_session = OnsiteSessionLocal()
        try:
            existing_ids = set(
                row[0] for row in
                b_session.query(OnsiteProblemDetail.task_id)
                .filter(OnsiteProblemDetail.task_id.in_(all_task_ids))
                .all()
            )
        finally:
            b_session.close()
        new_ids = [tid for tid in all_task_ids if tid not in existing_ids]
        skipped = len(all_task_ids) - len(new_ids)
        all_task_ids = new_ids
    else:
        skipped = 0

    if not all_task_ids:
        return {
            "success": True,
            "data": {"task_count": 0, "upserted": 0, "failed": 0, "skipped": skipped},
        }

    # ── 分片，多线程并行 ──
    tc = max(1, min(thread_count, len(all_task_ids)))
    slices: List[List[str]] = [[] for _ in range(tc)]
    for i, tid in enumerate(all_task_ids):
        slices[i % tc].append(tid)

    total_upserted = 0
    total_failed = 0
    all_errors: List[Dict[str, Any]] = []

    with ThreadPoolExecutor(max_workers=tc) as pool:
        futures = [pool.submit(_b_worker, sl, user_id) for sl in slices if sl]
        for fut in futures:
            r = fut.result()
            total_upserted += r.get("upserted", 0)
            total_failed += r.get("failed", 0)
            all_errors.extend(r.get("errors") or [])

    return {
        "success": True,
        "data": {
            "task_count": len(all_task_ids),
            "upserted": total_upserted,
            "failed": total_failed,
            "skipped": skipped,
            "errors": all_errors[:20],
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

    # Step 2: 从 A 表读任务 → TB Open API via proxy → 写 B 表（含评论+附件）
    b_res = sync_onsite_b_table_via_proxy(user_id)

    return {
        "success": a_res.get("success"),
        "data": {
            "a_sync": a_res.get("data") or {},
            "b_sync": b_res.get("data") or {},
        },
    }
