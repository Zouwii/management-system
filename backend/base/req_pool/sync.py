"""
需求池 — A/B 表同步逻辑.

A 表: req_pool_tasks (列表快照)
B 表: req_pool_details (明细, 解析 customField)
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select

from base.db.engine import ReqPoolSessionLocal, SessionLocal
from base.db.orm import Config as DbConfig, ReqPoolDetail, ReqPoolTask
from base.projects.task_service import query_project_tasks_service

# ── A 表游标持久化（断点续拉）─────────────────────────────────
_CURSOR_CONFIG_TYPE = "req_pool_a_cursor"


def _get_req_pool_a_cursor() -> Optional[str]:
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


def _set_req_pool_a_cursor(next_token: Optional[str]) -> None:
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


def reset_req_pool_a_cursor() -> Dict[str, Any]:
    """清空 A 表游标，下次同步从头开始."""
    cursor_before = _get_req_pool_a_cursor()
    _set_req_pool_a_cursor(None)
    return {
        "success": True,
        "data": {
            "was_active": cursor_before is not None,
            "cleared": True,
        },
    }


def get_req_pool_a_cursor_status() -> Dict[str, Any]:
    """查询当前 A 表游标状态."""
    cursor = _get_req_pool_a_cursor()
    return {
        "success": True,
        "data": {
            "active": cursor is not None,
            "next_token": cursor,
        },
    }

# ── 项目常量 ─────────────────────────────────────────────────
REQ_POOL_PROJECT_ID = "631710f1ac04e183d048d326"

# ── customField ID 常量 ──────────────────────────────────────
CF_REQ_SOURCE       = "631716de7f7344003f3ece70"  # 需求来源 (dropDown)
CF_TITLE            = "631715ae6b9968003f9d8663"  # 标题 (text)
CF_BRANCH           = "636243182a3467003f8421fd"  # 主干/分支 (dropDown)
CF_RELEASE_VERSION  = "650d01985926ce31ac8567ec"  # 发布版本 (dropDown)
CF_PACKAGE_VERSION  = "63ff1addd450590017455ec0"  # 子包版本 (text)
CF_PRD_DOC          = "634e8177cc2f290040ad67b5"  # PRD文档 (lookup2)
CF_DEV_DOC          = "634e81ba28f0e20040b97303"  # 研发文档 (lookup2)
CF_TEST_CASE        = "634e8825fddc0e003feca663"  # 测试用例 (lookup2)
CF_TEST_REPORT      = "634e81d65e75170040a27116"  # 测试报告 (lookup2)
CF_BIZ_OWNER        = "65f2ca0eae786a9021262156"  # 业务负责人 (lookup)


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
    cfs = item.get("customfields") or item.get("customFields") or []
    if not isinstance(cfs, list):
        return None
    for cf in cfs:
        if not isinstance(cf, dict):
            continue
        if str(cf.get("cfId") or cf.get("customFieldId") or cf.get("customfieldId") or "") != cfid:
            continue
        values = cf.get("value") or []
        if isinstance(values, list) and values:
            first = values[0]
            if isinstance(first, dict):
                return str(first.get("title") or "").strip() or None
            return str(first).strip() or None
    return None


def _str_list(lst: Any) -> Optional[List[str]]:
    if not isinstance(lst, list):
        return None
    return [str(x) for x in lst if x is not None]


# ── A 表写入 ─────────────────────────────────────────────────

def _apply_task_dict_to_req_a(obj: ReqPoolTask, d: Dict[str, Any], synced_at: datetime) -> None:
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
    cfs = d.get("customfields") or d.get("customFields") or []
    obj.customfield_ids = [str(cf.get("customfieldId") or cf.get("customFieldId") or "")
                           for cf in cfs if isinstance(cf, dict)
                           and (cf.get("customfieldId") or cf.get("customFieldId"))] or None
    try:
        obj.raw_json = json.dumps(d, ensure_ascii=False)
    except Exception:
        obj.raw_json = None
    obj.list_synced_at = synced_at


def sync_req_pool_a_table(payload: Dict[str, Any],
                           query_result: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    拉项目任务列表并 upsert A 表 req_pool_tasks.

    断点续拉：若 Config 表存有上次同步的 nextToken 游标，则接着上次的位置翻页；
    拉完全量后自动清除游标；force_refresh=True 时忽略游标从头拉.
    """
    payload = dict(payload or {})
    user_id = str(payload.get("userId") or payload.get("userid") or "").strip()
    force_refresh = bool(payload.get("force_refresh"))

    saved_cursor = None if force_refresh else _get_req_pool_a_cursor()

    if query_result is None:
        qp = {
            "userId": user_id,
            "projectId": REQ_POOL_PROJECT_ID,
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
    session = ReqPoolSessionLocal()
    upserted = 0
    try:
        for d in all_rows:
            if not isinstance(d, dict):
                continue
            pid = str(d.get("projectId") or "")
            tid = str(d.get("taskId") or "")
            if not pid or not tid:
                continue
            stmt = select(ReqPoolTask).where(
                ReqPoolTask.project_id == pid,
                ReqPoolTask.task_id == tid,
            )
            existing = session.scalars(stmt).first()
            if existing:
                _apply_task_dict_to_req_a(existing, d, now)
            else:
                row = ReqPoolTask()
                _apply_task_dict_to_req_a(row, d, now)
                session.add(row)
            upserted += 1
        session.commit()
    except Exception as e:
        session.rollback()
        return {"success": False, "error": str(e), "data": {}}
    finally:
        session.close()

    next_token = ding.get("nextToken")
    _set_req_pool_a_cursor(next_token)

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

def _upsert_req_detail_row(sess, task: Dict[str, Any], tid: str, user_id: str,
                            comments_json, attachments_json):
    """单条 B 表 upsert 逻辑."""
    from base.db.orm import ReqPoolDetail

    req_source = _extract_custom_field_title(task, CF_REQ_SOURCE)
    title = _extract_custom_field_title(task, CF_TITLE)
    branch = _extract_custom_field_title(task, CF_BRANCH)
    release_version = _extract_custom_field_title(task, CF_RELEASE_VERSION)
    package_version = _extract_custom_field_title(task, CF_PACKAGE_VERSION)
    prd_doc = _extract_custom_field_title(task, CF_PRD_DOC)
    dev_doc = _extract_custom_field_title(task, CF_DEV_DOC)
    test_case = _extract_custom_field_title(task, CF_TEST_CASE)
    test_report = _extract_custom_field_title(task, CF_TEST_REPORT)
    biz_owner = _extract_custom_field_title(task, CF_BIZ_OWNER)
    cfs = task.get("customfields") or task.get("customFields")
    try:
        raw_blob = json.dumps(task, ensure_ascii=False)
    except Exception:
        raw_blob = None

    now = datetime.now(timezone.utc)
    stmt = select(ReqPoolDetail).where(ReqPoolDetail.task_id == tid)
    row = sess.scalars(stmt).first()
    if row:
        row.content = str(task.get("content") or "")
        row.executor_id = str(task.get("executorId") or "")
        row.creator_id = str(task.get("creatorId") or "")
        row.scenario_field_config_id = str(task.get("scenarioFieldConfigId") or task.get("scenariofieldconfigId") or "")
        row.due_date = _parse_iso_dt(task.get("dueDate"))
        row.start_date = _parse_iso_dt(task.get("startDate"))
        row.is_done = bool(task.get("isDone"))
        row.is_archived = bool(task.get("isArchived"))
        row.priority = int(task.get("priority") or 0)
        row.progress = int(task.get("progress") or 0)
        row.note = str(task.get("note") or "")
        row.req_source = req_source
        row.title = title
        row.branch = branch
        row.release_version = release_version
        row.package_version = package_version
        row.prd_doc = prd_doc
        row.dev_doc = dev_doc
        row.test_case = test_case
        row.test_report = test_report
        row.biz_owner = biz_owner
        row.custom_fields_json = cfs
        row.raw_json = raw_blob
        row.comments_json = comments_json
        row.attachments_json = attachments_json
        row.fetched_at = now
    else:
        sess.add(ReqPoolDetail(
            project_id=str(task.get("projectId") or REQ_POOL_PROJECT_ID),
            task_id=tid,
            query_user_id=user_id,
            content=str(task.get("content") or ""),
            executor_id=str(task.get("executorId") or ""),
            creator_id=str(task.get("creatorId") or ""),
            scenario_field_config_id=str(task.get("scenarioFieldConfigId") or task.get("scenariofieldconfigId") or ""),
            due_date=_parse_iso_dt(task.get("dueDate")),
            start_date=_parse_iso_dt(task.get("startDate")),
            is_done=bool(task.get("isDone")),
            is_archived=bool(task.get("isArchived")),
            priority=int(task.get("priority") or 0),
            progress=int(task.get("progress") or 0),
            note=str(task.get("note") or ""),
            req_source=req_source,
            title=title,
            branch=branch,
            release_version=release_version,
            package_version=package_version,
            prd_doc=prd_doc,
            dev_doc=dev_doc,
            test_case=test_case,
            test_report=test_report,
            biz_owner=biz_owner,
            custom_fields_json=cfs,
            raw_json=raw_blob,
            comments_json=comments_json,
            attachments_json=attachments_json,
            fetched_at=now,
        ))


def _req_b_worker(task_ids: List[str], user_id: str) -> Dict[str, Any]:
    """单个线程的 B 表同步 worker：拉代理 API + upsert DB."""
    from base.onsite_problem.tb_proxy import fetch_task_with_comments

    upserted = 0
    failed = 0
    errors: List[Dict[str, Any]] = []
    sess = ReqPoolSessionLocal()
    pending = 0
    try:
        for tid in task_ids:
            try:
                result = fetch_task_with_comments(tid)
            except Exception as e:
                failed += 1
                errors.append({"task_id": tid, "error": str(e)})
                continue

            _upsert_req_detail_row(
                sess, result["task"], tid, user_id,
                result["comments_json"], result["attachments_json"],
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
    return {"upserted": upserted, "failed": failed, "errors": errors}


def sync_req_pool_b_table_via_proxy(user_id: str,
                                     thread_count: int = 5,
                                     skip_existing: bool = False) -> Dict[str, Any]:
    """
    从 A 表读取所有 task, 经 TB Open API via proxy 拉详情 + 评论 + 附件,
    多线程 upsert B 表 req_pool_details（含 comments_json + attachments_json）.
    """
    user_id = str(user_id).strip()
    if not user_id:
        return {"success": False, "error": "missing userId", "data": {}}

    from base.onsite_problem.tb_proxy import check_proxy_health

    # ── 预检：代理凭据是否有效 ──
    proxy_ok, proxy_msg = check_proxy_health()
    if not proxy_ok:
        return {"success": False, "error": f"TB 代理凭据无效: {proxy_msg}", "data": {}}

    a_session = ReqPoolSessionLocal()
    try:
        tasks = (
            a_session.query(ReqPoolTask)
            .filter(ReqPoolTask.project_id == REQ_POOL_PROJECT_ID)
            .all()
        )
        all_task_ids = [t.task_id for t in tasks if t.task_id]
    finally:
        a_session.close()

    if not all_task_ids:
        return {"success": True, "data": {"task_count": 0, "upserted": 0, "failed": 0}}

    if skip_existing:
        b_session = ReqPoolSessionLocal()
        try:
            existing_ids = set(
                row[0] for row in
                b_session.query(ReqPoolDetail.task_id)
                .filter(ReqPoolDetail.task_id.in_(all_task_ids))
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

    tc = max(1, min(thread_count, len(all_task_ids)))
    slices: List[List[str]] = [[] for _ in range(tc)]
    for i, tid in enumerate(all_task_ids):
        slices[i % tc].append(tid)

    total_upserted = 0
    total_failed = 0
    all_errors: List[Dict[str, Any]] = []

    with ThreadPoolExecutor(max_workers=tc) as pool:
        futures = [pool.submit(_req_b_worker, sl, user_id) for sl in slices if sl]
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

def sync_req_pool_full(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    全量同步：拉列表 → 写 A 表 → 写 B 表.
    """
    payload = dict(payload or {})
    user_id = str(payload.get("userId") or payload.get("userid") or "").strip()
    if not user_id:
        return {"success": False, "error": "missing userId", "data": {}}

    a_res = sync_req_pool_a_table({"userId": user_id, "force_refresh": True})
    if not a_res.get("success"):
        return {"success": False, "error": a_res.get("error", "A table sync failed"), "data": a_res}

    b_res = sync_req_pool_b_table_via_proxy(user_id)

    return {
        "success": a_res.get("success"),
        "data": {
            "a_sync": a_res.get("data") or {},
            "b_sync": b_res.get("data") or {},
        },
    }
