"""
将钉钉查询结果落库：A 表列表、B 表明细（模式 1 覆盖）。
"""

from __future__ import annotations

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select, text

from db.engine import SessionLocal
from db.orm import Config as DbConfig
from db.orm import ProjectTask, ProjectTaskDetail, ProjectTaskOverdueDetail, UpdateLock
from services.project_task_service import query_project_tasks_service, query_user_tasks_service
from services.workhour_util import parse_workhour_from_task_dict
from dingtalk_client import get_valid_access_token

DEFAULT_SCENARIO_FIELD_CONFIG_ID = "647854bcd999c893061ef8b5"  # 软件开发
DEFAULT_WORKHOUR_FIELD_ID = "64c8cad8485fb3987a5521b8"
OVERDUE_TAG_ID = "6527846cb6be8066fe331fd0"
DEFAULT_BUSINESS_TYPE_TAG_MAPPING = {
    "65264cfd697b6b909485bcbc": 0,  # 产品
    "65264cf79ed530912c3edf0f": 1,  # 研发
    "65264d01495638aacac3a9f9": 2,  # 订单
}
DEFAULT_TASK_FLOW_STATUS_MAPPING = {
    "680a31478c1bdfc448d36ed0": 0,  # 创建中
    "647854bcd999c893061ef89b": 1,  # 未完成
    "67fe5c1f142821dbe1328ddf": 2,  # 待评审
    "64785656c6215fd933a96631": 3,  # 评审中
    "647854bcd999c893061ef89c": 4,  # 已完成
    "64785656c6215fd933a96634": 5,  # 搁置
}

DEFAULT_UPDATE_LOCK_TTL_SEC = 60 * 30
DEFAULT_UPDATE_LOCK_KEY = "workhour_update:all"


def _zhr_temp_log_elapsed(biz: str, step: str, t0: float, extra: Optional[Dict[str, Any]] = None) -> None:
    cost_ms = round((time.perf_counter() - t0) * 1000, 2)
    if extra:
        print("ZHR TEMP [{}] {} cost_ms={} extra={}".format(biz, step, cost_ms, extra))
    else:
        print("ZHR TEMP [{}] {} cost_ms={}".format(biz, step, cost_ms))


def _acquire_update_lock(lock_key: str, owner: str, ttl_sec: int = DEFAULT_UPDATE_LOCK_TTL_SEC) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    expires = now + timedelta(seconds=max(int(ttl_sec or 0), 1))
    sess = SessionLocal()
    try:
        row = sess.query(UpdateLock).filter(UpdateLock.lock_key == str(lock_key)).first()
        if row:
            row_exp = _cmp_dt_utc(getattr(row, "expires_at", None))
            if row_exp and row_exp > now and str(getattr(row, "owner", "") or "") != str(owner):
                return {
                    "ok": False,
                    "error": "update is in progress by another user",
                    "lock": {
                        "lock_key": str(lock_key),
                        "owner": str(getattr(row, "owner", "") or ""),
                        "expires_at": row_exp.isoformat(),
                    },
                }
            row.owner = str(owner)
            row.locked_at = now
            row.expires_at = expires
        else:
            sess.add(
                UpdateLock(
                    lock_key=str(lock_key),
                    owner=str(owner),
                    locked_at=now,
                    expires_at=expires,
                )
            )
        sess.commit()
        return {"ok": True, "lock": {"lock_key": str(lock_key), "owner": str(owner), "expires_at": expires.isoformat()}}
    except Exception as e:
        sess.rollback()
        return {"ok": False, "error": str(e), "lock": {"lock_key": str(lock_key), "owner": str(owner)}}
    finally:
        sess.close()


def _release_update_lock(lock_key: str, owner: str) -> None:
    sess = SessionLocal()
    try:
        row = sess.query(UpdateLock).filter(UpdateLock.lock_key == str(lock_key)).first()
        if row and str(getattr(row, "owner", "") or "") == str(owner):
            sess.delete(row)
            sess.commit()
    except Exception:
        sess.rollback()
    finally:
        sess.close()


def _get_update_lock_status(lock_key: str = DEFAULT_UPDATE_LOCK_KEY) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    sess = SessionLocal()
    try:
        row = sess.query(UpdateLock).filter(UpdateLock.lock_key == str(lock_key)).first()
        if not row:
            return {"locked": False, "lock": {}}
        row_exp = _cmp_dt_utc(getattr(row, "expires_at", None))
        if row_exp and row_exp > now:
            return {
                "locked": True,
                "lock": {
                    "lock_key": str(lock_key),
                    "owner": str(getattr(row, "owner", "") or ""),
                    "expires_at": row_exp.isoformat(),
                },
            }
        # 锁已过期：清理脏锁，避免阻塞后续操作
        sess.delete(row)
        sess.commit()
        return {"locked": False, "lock": {}}
    except Exception as e:
        sess.rollback()
        return {"locked": False, "error": str(e), "lock": {}}
    finally:
        sess.close()


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


def _cmp_dt_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _format_dt_for_tql_utc(dt: datetime) -> str:
    d = dt.astimezone(timezone.utc).replace(microsecond=0)
    return d.strftime("%Y-%m-%dT%H:%M:%S") + ".000Z"


def _get_config_value(type_: str) -> str:
    sess = SessionLocal()
    try:
        row = sess.query(DbConfig).filter(DbConfig.type_ == str(type_)).first()
        return str(getattr(row, "value", "") or "") if row else ""
    finally:
        sess.close()


def _upsert_config_value(type_: str, value: str) -> None:
    sess = SessionLocal()
    try:
        row = sess.query(DbConfig).filter(DbConfig.type_ == str(type_)).first()
        if row:
            row.value = str(value)
        else:
            sess.add(DbConfig(type_=str(type_), value=str(value), brief=None))
        sess.commit()
    finally:
        sess.close()


def _extract_detail_item(dres: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    ding = ((dres.get("data") or {}).get("dingtalk")) or {}
    raw_result = ding.get("result")
    if isinstance(raw_result, list) and raw_result:
        first = raw_result[0]
        return first if isinstance(first, dict) else None
    if isinstance(raw_result, dict):
        return raw_result
    return None


def _sync_one_detail_to_b_and_c(
    one_session,
    *,
    executor_id: str,
    task_id: str,
    project_id: str,
    item: Dict[str, Any],
    field_id: str,
    now: datetime,
    business_type_mapping: Dict[str, int],
    task_flow_status_mapping: Dict[str, int],
    write_b: bool,
    write_c: bool,
) -> Dict[str, Any]:
    tag_ids = item.get("tagIds") or item.get("tagids") or []
    is_overdue = False
    if isinstance(tag_ids, list):
        for t in tag_ids:
            if str(t) == OVERDUE_TAG_ID:
                is_overdue = True
                break

    business_type = _resolve_business_type_from_tags(
        [str(x) for x in tag_ids] if isinstance(tag_ids, list) else [],
        business_type_mapping,
    )
    task_flow_status_id = _resolve_task_flow_status_id(item, task_flow_status_mapping)
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

    if write_b:
        stmt = select(ProjectTaskDetail).where(
            ProjectTaskDetail.task_id == task_id,
            ProjectTaskDetail.query_user_id == executor_id,
        )
        row = one_session.scalars(stmt).first()
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
            row.business_type = business_type
            row.task_flow_status_id = task_flow_status_id
            row.fetched_at = now
        else:
            one_session.add(
                ProjectTaskDetail(
                    project_id=project_id,
                    task_id=task_id,
                    query_user_id=executor_id,
                    work_hour_field_id=field_id,
                    work_hour=wh,
                    custom_fields_json=cfs if cfs is not None else None,
                    raw_json=raw_blob,
                    parent_task_id=str(item.get("parentTaskId") or "") or None,
                    task_list_id=str(item.get("taskListId") or "") or None,
                    task_stage_id=str(item.get("taskStageId") or item.get("stageId") or "") or None,
                    unique_id=unique_id,
                    is_overdue=is_overdue,
                    business_type=business_type,
                    task_flow_status_id=task_flow_status_id,
                    fetched_at=now,
                )
            )

    if write_c:
        stmt2 = select(ProjectTaskOverdueDetail).where(
            ProjectTaskOverdueDetail.task_id == task_id,
            ProjectTaskOverdueDetail.query_user_id == executor_id,
            ProjectTaskOverdueDetail.project_id == project_id,
        )
        row2 = one_session.scalars(stmt2).first()
        if is_overdue:
            if row2:
                row2.work_hour = wh
                row2.business_type = business_type
                row2.task_flow_status_id = task_flow_status_id
                row2.custom_fields_json = cfs if cfs is not None else None
                row2.raw_json = raw_blob
                row2.fetched_at = now
            else:
                one_session.add(
                    ProjectTaskOverdueDetail(
                        project_id=project_id,
                        task_id=task_id,
                        query_user_id=executor_id,
                        work_hour=wh,
                        business_type=business_type,
                        task_flow_status_id=task_flow_status_id,
                        custom_fields_json=cfs if cfs is not None else None,
                        raw_json=raw_blob,
                        fetched_at=now,
                    )
                )
        else:
            # 逾期标签可能被去掉：保持 C 为“当前逾期快照”，若存在则删掉
            if row2:
                one_session.delete(row2)

    return {"work_hour": wh, "is_overdue": is_overdue}


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


def _get_business_type_tag_mapping() -> Dict[str, int]:
    session = SessionLocal()
    try:
        row = session.query(DbConfig).filter(DbConfig.type_ == "business_type_tag_mapping").first()
        if not row or not str(getattr(row, "value", "") or "").strip():
            return dict(DEFAULT_BUSINESS_TYPE_TAG_MAPPING)
        try:
            raw = json.loads(str(row.value))
        except Exception:
            return dict(DEFAULT_BUSINESS_TYPE_TAG_MAPPING)
        if not isinstance(raw, dict):
            return dict(DEFAULT_BUSINESS_TYPE_TAG_MAPPING)
        out: Dict[str, int] = {}
        for k, v in raw.items():
            kk = str(k or "").strip()
            if not kk:
                continue
            try:
                out[kk] = int(v)
            except Exception:
                continue
        return out or dict(DEFAULT_BUSINESS_TYPE_TAG_MAPPING)
    finally:
        session.close()


def _resolve_business_type_from_tags(tag_ids: List[str], mapping: Dict[str, int]) -> Optional[int]:
    # 命中多个时按 tagIds 顺序取第一个
    for t in tag_ids or []:
        tt = str(t or "").strip()
        if not tt:
            continue
        if tt in mapping:
            return int(mapping[tt])
    return None


def _get_task_flow_status_mapping() -> Dict[str, int]:
    session = SessionLocal()
    try:
        row = session.query(DbConfig).filter(DbConfig.type_ == "task_flow_status_mapping").first()
        if not row or not str(getattr(row, "value", "") or "").strip():
            return dict(DEFAULT_TASK_FLOW_STATUS_MAPPING)
        try:
            raw = json.loads(str(row.value))
        except Exception:
            return dict(DEFAULT_TASK_FLOW_STATUS_MAPPING)
        if not isinstance(raw, dict):
            return dict(DEFAULT_TASK_FLOW_STATUS_MAPPING)
        out: Dict[str, int] = {}
        for k, v in raw.items():
            kk = str(k or "").strip()
            if not kk:
                continue
            try:
                out[kk] = int(v)
            except Exception:
                continue
        return out or dict(DEFAULT_TASK_FLOW_STATUS_MAPPING)
    finally:
        session.close()


def _resolve_task_flow_status_id(item: Dict[str, Any], mapping: Dict[str, int]) -> Optional[int]:
    raw = (
        item.get("taskflowStatusId")
        or item.get("taskflowstatusId")
        or item.get("taskFlowStatusId")
        or ""
    )
    key = str(raw or "").strip()
    if not key:
        return None
    if key in mapping:
        return int(mapping[key])
    return None


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


def full_update_service(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    全量更新封装（按钮专用，简化版）：
    1) 触发 update_endtime（将 config.end_time 日期更新为今天）
    2) 读取 end_time 并计算最近一年窗口（startDue/endDue）
    3) 直接清空 B/C 表全部数据
    4) 按最近一年窗口同步 A，再按原有 3 线程轮循逻辑回填 B/C
    """
    payload = dict(payload or {})
    _t_all = time.perf_counter()
    user_id = str(payload.get("userId") or payload.get("userid") or "").strip()
    project_id = str(payload.get("projectId") or payload.get("projectid") or "").strip()
    if not user_id or not project_id:
        return {"success": False, "error": "missing userId or projectId", "data": {}}

    # 1) update_endtime：把 end_time 日期更新为今天（UTC）
    from services.config_service import update_endtime_service
    _t = time.perf_counter()
    upd = update_endtime_service() or {}
    _zhr_temp_log_elapsed("full_update", "update_endtime_service", _t)
    if not upd.get("success"):
        return {"success": False, "error": upd.get("error", "update_endtime failed"), "data": upd.get("data") or {}}

    # 2) read_config_make_range：读取 end_time 并计算最近一年窗口
    from db.engine import SessionLocal
    from db.orm import Config as DbConfig

    _t = time.perf_counter()
    sess = SessionLocal()
    try:
        end_row = sess.query(DbConfig).filter(DbConfig.type_ == "end_time").first()
        end_raw = str(getattr(end_row, "value", "") or "").strip() if end_row else ""
    finally:
        sess.close()
    if not end_raw:
        return {"success": False, "error": "missing config end_time", "data": {}}
    _zhr_temp_log_elapsed("full_update", "read_end_time_and_make_range", _t, {"end_raw": end_raw})

    end_dt = _parse_iso_dt(end_raw)
    if not end_dt:
        return {"success": False, "error": "invalid config end_time", "data": {}}

    # end_time 由 config 给出（季度末）；start_time 按“今天往前一年”计算
    if end_dt.tzinfo is None:
        end_dt = end_dt.replace(tzinfo=timezone.utc)
    else:
        end_dt = end_dt.astimezone(timezone.utc)

    def _subtract_one_year_local(dt: datetime) -> datetime:
        try:
            return dt.replace(year=dt.year - 1)
        except ValueError:
            day = min(dt.day, 28)
            return dt.replace(year=dt.year - 1, day=day)

    def _format_dt_for_tql_local(dt: datetime) -> str:
        d = dt.astimezone(timezone.utc).replace(microsecond=0)
        return d.strftime("%Y-%m-%dT%H:%M:%S") + ".000Z"

    now_utc = datetime.now(timezone.utc)
    start_dt = _subtract_one_year_local(now_utc)
    start_due = _format_dt_for_tql_local(start_dt)
    end_due = _format_dt_for_tql_local(end_dt)

    # 3) 直接清空 B/C 全表
    _t = time.perf_counter()
    wipe_sess = SessionLocal()
    try:
        wiped_b = wipe_sess.query(ProjectTaskDetail).delete(synchronize_session=False)
        wiped_c = wipe_sess.query(ProjectTaskOverdueDetail).delete(synchronize_session=False)
        # 删除后重置自增序列，保证新写入从 1 开始（不同数据库方言分别处理）。
        dialect = str(getattr(getattr(wipe_sess, "bind", None), "dialect", None).name or "")
        if dialect == "sqlite":
            wipe_sess.execute(
                text(
                    "DELETE FROM sqlite_sequence "
                    "WHERE name IN ('project_task_details', 'project_task_overdue_details')"
                )
            )
        elif dialect in {"mysql", "mariadb"}:
            wipe_sess.execute(text("ALTER TABLE project_task_details AUTO_INCREMENT = 1"))
            wipe_sess.execute(text("ALTER TABLE project_task_overdue_details AUTO_INCREMENT = 1"))
        elif dialect == "postgresql":
            wipe_sess.execute(text("TRUNCATE TABLE project_task_details, project_task_overdue_details RESTART IDENTITY"))
        wipe_sess.commit()
    except Exception as e:
        wipe_sess.rollback()
        return {"success": False, "error": "wipe B/C failed: {}".format(str(e)), "data": {}}
    finally:
        wipe_sess.close()
    _zhr_temp_log_elapsed("full_update", "wipe_b_c", _t, {"b_deleted": int(wiped_b or 0), "c_deleted": int(wiped_c or 0)})

    # 4) A 表：按 startDue/endDue 同步（软件开发场景过滤由 sync_project_tasks_to_db 完成）
    max_results = int(payload.get("maxResults", 500) or 500)
    max_pages = int(payload.get("maxPages", 200) or 200)
    a_payload = dict(payload)
    a_payload.update(
        {
            "userId": user_id,
            "projectId": project_id,
            "query": "(dueDate >= '{start}') AND (dueDate <= '{end}')".format(start=start_due, end=end_due),
            "maxResults": max_results,
            "maxPages": max_pages,
            "force_refresh": True,
        }
    )
    _t = time.perf_counter()
    a_out = sync_project_tasks_to_db(a_payload)
    _zhr_temp_log_elapsed("full_update", "sync_A", _t, {"maxResults": max_results, "maxPages": max_pages})
    if not a_out.get("success"):
        return {"success": False, "error": a_out.get("error", "sync A failed"), "data": a_out.get("data") or {}}

    # 5) B/C：固定 3 线程轮循（复用 all_time_download 的实现）
    bc_payload = dict(payload)
    bc_payload.update(
        {
            "userId": user_id,
            "projectId": project_id,
            # B 表过滤窗口：全量更新按最近一年口径
            "startDate": start_due,
            "endDate": end_due,
            # A 表窗口：同样使用 endDate 推导（实现里会再 subtract one year）
            "endDate": end_due,
        }
    )
    _t = time.perf_counter()
    bc_out = _all_time_download_impl(bc_payload)
    _zhr_temp_log_elapsed("full_update", "sync_BC", _t)
    if not bc_out.get("success"):
        return {"success": False, "error": bc_out.get("error", "sync B/C failed"), "data": bc_out.get("data") or {}}
    _zhr_temp_log_elapsed("full_update", "total", _t_all, {"projectId": project_id, "userId": user_id})

    return {
        "success": True,
        "data": {
            "updated_end_time": upd.get("end_time"),
            "startDue": start_due,
            "endDue": end_due,
            "wiped": {"b_deleted": int(wiped_b or 0), "c_deleted": int(wiped_c or 0)},
            "syncA": a_out.get("data") or {},
            "syncBC": bc_out.get("data") or {},
        },
    }


def _all_time_download_impl(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    B/C 同步实现（仅基于现有 A 表）：
    - 读取 endDate（缺省回退 config.end_time）计算最近一年窗口，用于从 A 表筛任务
    - 严格使用 payload.startDate/endDate 作为“写入 B 表的阈值窗口”
    - 固定 3 线程轮循拉详情并 upsert B/C
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

    # 1) 读取结束时间（优先前端传入 endDate，其次 config.end_time），算最近一年窗口并写入 A 表
    from db.orm import Config as DbConfig

    session = SessionLocal()
    try:
        end_row = session.query(DbConfig).filter(DbConfig.type_ == "end_time").first()
    finally:
        session.close()

    end_raw = payload.get("endDate") or payload.get("end_time")
    if not end_raw and end_row:
        end_raw = end_row.value
    if not end_raw:
        return {"success": False, "error": "missing endDate and config end_time", "data": {}}

    end_dt = _cmp_dt(_parse_iso_dt(end_raw))
    if not end_dt:
        return {"success": False, "error": "invalid endDate/config end_time", "data": {}}

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

    # 2) 从 A 表取出要轮循拉详情的 task 列表（软件开发 + 最近一年窗口）
    # 同时：B 表写入阈值窗口严格使用 payload.startDate/endDate
    cfg_start_raw = payload.get("startDate") or payload.get("start_time")
    cfg_end_raw = payload.get("endDate") or payload.get("end_time")
    cfg_start_dt = _cmp_dt(_parse_iso_dt(cfg_start_raw))
    cfg_end_dt = _cmp_dt(_parse_iso_dt(cfg_end_raw))
    if not cfg_start_dt or not cfg_end_dt:
        return {"success": False, "error": "missing or invalid startDate/endDate", "data": {}}

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

    # 3) B/C：不做 project 全量删写；只清理“本次窗口未包含”的 task 行
    #    这样 stats（不按时间窗过滤）仍然能保持 B/C 是“当前窗口快照”，同时避免整项目擦除。
    eligible_by_executor: Dict[str, set] = {}
    for spec in task_specs:
        ex_id = str(spec.get("executor_id") or "").strip()
        t_id = str(spec.get("task_id") or "").strip()
        if not ex_id or not t_id:
            continue
        eligible_by_executor.setdefault(ex_id, set()).add(t_id)

    if eligible_by_executor:
        del_sess = SessionLocal()
        try:
            for ex_id, tids in eligible_by_executor.items():
                tids_list = list(tids)
                if tids_list:
                    del_sess.query(ProjectTaskDetail).filter(
                        ProjectTaskDetail.project_id == project_id,
                        ProjectTaskDetail.query_user_id == ex_id,
                        ProjectTaskDetail.task_id.notin_(tids_list),
                    ).delete(synchronize_session=False)
                    del_sess.query(ProjectTaskOverdueDetail).filter(
                        ProjectTaskOverdueDetail.project_id == project_id,
                        ProjectTaskOverdueDetail.query_user_id == ex_id,
                        ProjectTaskOverdueDetail.task_id.notin_(tids_list),
                    ).delete(synchronize_session=False)
            del_sess.commit()
        finally:
            del_sess.close()

    # 4) 3 线程并发轮循拉详情 + eligible 判断 + upsert B
    field_id = str(
        payload.get("workHourFieldId")
        or os.getenv("TB_TOOL_BT_WORKHOUR_FIELD_ID")
        or os.getenv("TB_TOOL_B1_WORKHOUR_FIELD_ID")
        or DEFAULT_WORKHOUR_FIELD_ID
    )
    business_type_mapping = _get_business_type_tag_mapping()
    task_flow_status_mapping = _get_task_flow_status_mapping()

    token_result = get_valid_access_token(payload or {})
    if not token_result.get("ok"):
        return {"success": False, "error": token_result.get("error", "failed to fetch dingtalk token"), "data": {}}
    access_token = token_result.get("access_token")

    # 按你的要求固定 3 条线程轮循
    thread_count = 3
    business_type_mapping = _get_business_type_tag_mapping()
    task_flow_status_mapping = _get_task_flow_status_mapping()

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
        business_type: Optional[int],
        task_flow_status_id: Optional[int],
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
            row.business_type = business_type
            row.task_flow_status_id = task_flow_status_id
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
                    business_type=business_type,
                    task_flow_status_id=task_flow_status_id,
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
        business_type: Optional[int],
        task_flow_status_id: Optional[int],
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
            row.business_type = business_type
            row.task_flow_status_id = task_flow_status_id
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
                    business_type=business_type,
                    task_flow_status_id=task_flow_status_id,
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
                business_type = _resolve_business_type_from_tags(
                    [str(x) for x in tag_ids] if isinstance(tag_ids, list) else [],
                    business_type_mapping,
                )
                task_flow_status_id = _resolve_task_flow_status_id(item, task_flow_status_mapping)
                task_flow_status_id = _resolve_task_flow_status_id(item, task_flow_status_mapping)
                business_type = _resolve_business_type_from_tags(
                    [str(x) for x in tag_ids] if isinstance(tag_ids, list) else [],
                    business_type_mapping,
                )

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
                        business_type=business_type,
                        task_flow_status_id=task_flow_status_id,
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
                        business_type=business_type,
                        task_flow_status_id=task_flow_status_id,
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
            "sync": {},
            "tasks": tasks,
            "b_sync": {
                "window": {"start": start_iso, "end": end_iso},
                "task_count_in_a": len(task_specs),
                "b_upserts": b_upserts,
                "b_skipped": b_skipped,
                "b_fail": b_fail,
                "failures": b_failures[:20],
                "mode": "upsert-cleanup",
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
    business_type_mapping = _get_business_type_tag_mapping()
    business_type = _resolve_business_type_from_tags(
        [str(x) for x in tag_ids] if isinstance(tag_ids, list) else [],
        business_type_mapping,
    )
    task_flow_status_mapping = _get_task_flow_status_mapping()
    task_flow_status_id = _resolve_task_flow_status_id(item, task_flow_status_mapping)
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
            row.business_type = business_type
            row.task_flow_status_id = task_flow_status_id
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
                    business_type=business_type,
                    task_flow_status_id=task_flow_status_id,
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


def sync_project_details_in_time_range_service(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    仅使用 payload.startDate/endDate 作为窗口（不再读取/回退 config）：
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

    # 解析窗口：仅允许 payload
    start_dt = _parse_iso_dt(payload.get("startDate") or payload.get("start_time") or payload.get("startTime"))
    end_dt = _parse_iso_dt(payload.get("endDate") or payload.get("end_time") or payload.get("endTime"))

    if not start_dt or not end_dt:
        return {"success": False, "error": "missing or invalid startDate/endDate", "data": {}}

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

    # 从 A 表取窗口内任务，同步到 B 表：仅对 task 维度 upsert（不 project 全删）

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

    # 2.5) B/C：只清理“本次窗口未包含”的 task 行（避免项目/区间间残留）
    eligible_by_executor: Dict[str, set] = {}
    for spec in task_specs:
        ex_id = str(spec.get("executor_id") or "").strip()
        t_id = str(spec.get("task_id") or "").strip()
        if not ex_id or not t_id:
            continue
        eligible_by_executor.setdefault(ex_id, set()).add(t_id)

    if eligible_by_executor:
        del_sess = SessionLocal()
        try:
            for ex_id, tids in eligible_by_executor.items():
                tids_list = list(tids)
                if not tids_list:
                    continue
                del_sess.query(ProjectTaskDetail).filter(
                    ProjectTaskDetail.project_id == project_id,
                    ProjectTaskDetail.query_user_id == ex_id,
                    ProjectTaskDetail.task_id.notin_(tids_list),
                ).delete(synchronize_session=False)
                del_sess.query(ProjectTaskOverdueDetail).filter(
                    ProjectTaskOverdueDetail.project_id == project_id,
                    ProjectTaskOverdueDetail.query_user_id == ex_id,
                    ProjectTaskOverdueDetail.task_id.notin_(tids_list),
                ).delete(synchronize_session=False)
            del_sess.commit()
        finally:
            del_sess.close()

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
                    row.business_type = business_type
                    row.task_flow_status_id = task_flow_status_id
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
                            business_type=business_type,
                            task_flow_status_id=task_flow_status_id,
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
                "mode": "upsert-cleanup",
            },
        },
    }


def normal_incremental_update_service(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    普通更新（按钮专用，增量模式）：
    1) 读取 config.last_update_time；同时取当前北京时间 now_bj
    2) 从 payload 获取 startDue/endDue（缺省则回退 config.start_time/end_time）
    3) 钉钉增量查询：created >= last_update_time
    4) 对增量查询结果：写入 A，并对“新增/变更任务”写入 B/C
    5) 用 startDue/endDue 从 A 表筛任务，按 eligible 清理后 3 线程轮循更新 B
    6) 单独对 C 表（当前逾期快照）做状态刷新（逾期->保留/更新，非逾期->删除）
    """
    payload = dict(payload or {})
    _t_all = time.perf_counter()
    user_id = str(payload.get("userId") or payload.get("userid") or "").strip()
    project_id = str(payload.get("projectId") or payload.get("projectid") or "").strip()
    if not user_id or not project_id:
        return {"success": False, "error": "missing userId or projectId", "data": {}}

    # 1) 北京时间 + last_update_time
    bj_tz = timezone(timedelta(hours=8))
    now_bj = datetime.now(bj_tz)
    _t = time.perf_counter()
    last_raw = _get_config_value("last_update_time")
    last_dt = _cmp_dt_utc(_parse_iso_dt(last_raw)) if last_raw else None
    _zhr_temp_log_elapsed("normal_update", "read_last_update_time", _t, {"last_update_time": last_raw or ""})

    # 2) 时间窗口：仅允许 payload.start_time / payload.end_time
    start_raw = payload.get("start_time")
    end_raw = payload.get("end_time")
    start_dt = _cmp_dt_utc(_parse_iso_dt(str(start_raw or "")))
    end_dt = _cmp_dt_utc(_parse_iso_dt(str(end_raw or "")))
    if not start_dt or not end_dt:
        return {"success": False, "error": "missing or invalid payload.start_time/end_time", "data": {}}

    # last_update_time 缺省时：用 start_dt 作为增量起点，避免全量打爆
    if not last_dt:
        last_dt = start_dt
        last_raw = _format_dt_for_tql_utc(last_dt)

    created_threshold = _format_dt_for_tql_utc(last_dt)
    now_utc_dt = now_bj.astimezone(timezone.utc)
    created_upper = _format_dt_for_tql_utc(now_utc_dt)

    max_results = int(payload.get("maxResults", 500) or 500)
    max_pages = int(payload.get("maxPages", 200) or 200)

    # 3) 钉钉增量拉列表：created >= last_update_time AND created <= 当前时刻
    inc_payload = dict(payload)
    inc_payload.update(
        {
            "userId": user_id,
            "projectId": project_id,
            "query": "(created >= '{t0}') AND (created <= '{t1}')".format(
                t0=created_threshold, t1=created_upper
            ),
            "maxResults": max_results,
            "maxPages": max_pages,
            "force_refresh": True,
        }
    )
    _t = time.perf_counter()
    inc_res = query_project_tasks_service(inc_payload)
    _zhr_temp_log_elapsed("normal_update", "query_incremental_A", _t, {"query": inc_payload.get("query", "")})
    if not inc_res.get("success"):
        return {"success": False, "error": inc_res.get("error", "incremental query failed"), "data": inc_res}

    # 4) 写 A；并对增量结果的任务写 B/C
    _t = time.perf_counter()
    a_out = sync_project_tasks_to_db(inc_payload, query_result=inc_res)
    _zhr_temp_log_elapsed("normal_update", "upsert_A", _t)
    if not a_out.get("success"):
        return {"success": False, "error": a_out.get("error", "sync A failed"), "data": a_out.get("data") or {}}

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
    business_type_mapping = _get_business_type_tag_mapping()
    task_flow_status_mapping = _get_task_flow_status_mapping()

    ding = (inc_res.get("data") or {}).get("dingtalk") or {}
    all_rows = ding.get("result") if isinstance(ding.get("result"), list) else []
    scenario_id = str(payload.get("scenarioFieldConfigId") or DEFAULT_SCENARIO_FIELD_CONFIG_ID)
    inc_specs: List[Dict[str, str]] = []
    for r in all_rows:
        if not isinstance(r, dict):
            continue
        sid = str(r.get("scenariofieldconfigId") or r.get("scenarioFieldConfigId") or "")
        if sid != scenario_id:
            continue
        tid = str(r.get("taskId") or "").strip()
        ex = str(r.get("executorId") or "").strip()
        if not tid or not ex:
            continue
        inc_specs.append({"task_id": tid, "executor_id": ex, "project_id": project_id})

    inc_ok = 0
    inc_fail = 0
    inc_failures: List[Dict[str, Any]] = []
    _t = time.perf_counter()
    if inc_specs:
        sess = SessionLocal()
        try:
            for spec in inc_specs:
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
                    inc_fail += 1
                    inc_failures.append({"taskId": spec["task_id"], "executorId": spec["executor_id"], "error": dres.get("error")})
                    continue
                item = _extract_detail_item(dres)
                if not item:
                    inc_fail += 1
                    inc_failures.append({"taskId": spec["task_id"], "executorId": spec["executor_id"], "error": "empty detail"})
                    continue
                now = datetime.now(timezone.utc)
                _sync_one_detail_to_b_and_c(
                    sess,
                    executor_id=spec["executor_id"],
                    task_id=spec["task_id"],
                    project_id=spec["project_id"],
                    item=item,
                    field_id=field_id,
                    now=now,
                    business_type_mapping=business_type_mapping,
                    task_flow_status_mapping=task_flow_status_mapping,
                    write_b=True,
                    write_c=True,
                )
                sess.commit()
                inc_ok += 1
        finally:
            sess.close()
    _zhr_temp_log_elapsed("normal_update", "incremental_fill_BC", _t, {"inc_count": len(inc_specs), "ok": inc_ok, "fail": inc_fail})

    # 5) 用 startDue/endDue 从 A 表筛选范围任务，3 线程更新 B（仅更新内容，不做清理删除）
    start_iso = _format_dt_for_tql_utc(start_dt)
    end_iso = _format_dt_for_tql_utc(end_dt)

    _t = time.perf_counter()
    session = SessionLocal()
    task_specs: List[Dict[str, Any]] = []
    try:
        rows: List[ProjectTask] = (
            session.query(ProjectTask)
            .filter(ProjectTask.project_id == project_id)
            .filter(ProjectTask.scenario_field_config_id == DEFAULT_SCENARIO_FIELD_CONFIG_ID)
            .order_by(ProjectTask.task_id)
            .all()
        )
        for r in rows:
            ex = str(r.executor_id or "").strip()
            tid = str(r.task_id or "").strip()
            if not ex or not tid:
                continue
            due_dt = _cmp_dt_utc(r.due_date)
            in_range = bool(due_dt and start_dt <= due_dt <= end_dt)
            if not in_range:
                continue
            task_specs.append({"task_id": tid, "executor_id": ex, "project_id": project_id})
    finally:
        session.close()
    _zhr_temp_log_elapsed("normal_update", "load_A_window_tasks", _t, {"task_count": len(task_specs)})

    thread_count = 3
    specs_by_worker: List[List[Dict[str, str]]] = [[] for _ in range(thread_count)]
    for idx, spec in enumerate(task_specs):
        specs_by_worker[idx % thread_count].append(spec)

    def _b_worker(slice_specs: List[Dict[str, str]]) -> Dict[str, Any]:
        ok_upserts = 0
        fail_count = 0
        failures: List[Dict[str, Any]] = []
        one_session = SessionLocal()
        try:
            for spec in slice_specs:
                q_payload = {
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
                    failures.append({"taskId": spec["task_id"], "executorId": spec["executor_id"], "error": dres.get("error")})
                    continue
                item = _extract_detail_item(dres)
                if not item:
                    fail_count += 1
                    failures.append({"taskId": spec["task_id"], "executorId": spec["executor_id"], "error": "empty detail"})
                    continue
                now = datetime.now(timezone.utc)
                _sync_one_detail_to_b_and_c(
                    one_session,
                    executor_id=spec["executor_id"],
                    task_id=spec["task_id"],
                    project_id=spec["project_id"],
                    item=item,
                    field_id=field_id,
                    now=now,
                    business_type_mapping=business_type_mapping,
                    task_flow_status_mapping=task_flow_status_mapping,
                    write_b=True,
                    write_c=False,
                )
                one_session.commit()
                ok_upserts += 1
        finally:
            one_session.close()
        return {"ok_upserts": ok_upserts, "fail_count": fail_count, "failures": failures}

    b_upserts = 0
    b_fail = 0
    b_failures: List[Dict[str, Any]] = []
    _t = time.perf_counter()
    with ThreadPoolExecutor(max_workers=thread_count) as pool:
        futures = [pool.submit(_b_worker, ss) for ss in specs_by_worker if ss]
        for fut in futures:
            r = fut.result()
            b_upserts += int(r.get("ok_upserts", 0) or 0)
            b_fail += int(r.get("fail_count", 0) or 0)
            b_failures.extend(r.get("failures") or [])
    _zhr_temp_log_elapsed("normal_update", "window_refresh_B", _t, {"ok": b_upserts, "fail": b_fail})

    # 6) 存量 C 复查：从 C 表现有记录出发逐条查询
    #    - 若已非逾期：写回 B，并从 C 删除
    #    - 若仍逾期但内容/状态变动：更新 C
    c_specs: List[Dict[str, str]] = []
    cscan_sess = SessionLocal()
    try:
        c_rows = (
            cscan_sess.query(ProjectTaskOverdueDetail)
            .filter(ProjectTaskOverdueDetail.project_id == project_id)
            .all()
        )
        for r in c_rows:
            task_id = str(getattr(r, "task_id", "") or "").strip()
            ex_id = str(getattr(r, "query_user_id", "") or "").strip()
            if task_id and ex_id:
                c_specs.append({"task_id": task_id, "executor_id": ex_id, "project_id": project_id})
    finally:
        cscan_sess.close()

    def _c_worker(slice_specs: List[Dict[str, str]]) -> Dict[str, Any]:
        ok_count = 0
        fail_count = 0
        failures: List[Dict[str, Any]] = []
        one_session = SessionLocal()
        try:
            for spec in slice_specs:
                q_payload = {
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
                    failures.append({"taskId": spec["task_id"], "executorId": spec["executor_id"], "error": dres.get("error")})
                    continue
                item = _extract_detail_item(dres)
                if not item:
                    fail_count += 1
                    failures.append({"taskId": spec["task_id"], "executorId": spec["executor_id"], "error": "empty detail"})
                    continue
                now = datetime.now(timezone.utc)
                _sync_one_detail_to_b_and_c(
                    one_session,
                    executor_id=spec["executor_id"],
                    task_id=spec["task_id"],
                    project_id=spec["project_id"],
                    item=item,
                    field_id=field_id,
                    now=now,
                    business_type_mapping=business_type_mapping,
                    task_flow_status_mapping=task_flow_status_mapping,
                    write_b=True,
                    write_c=True,
                )
                one_session.commit()
                ok_count += 1
        finally:
            one_session.close()
        return {"ok_count": ok_count, "fail_count": fail_count, "failures": failures}

    c_ok = 0
    c_fail = 0
    c_failures: List[Dict[str, Any]] = []
    _t = time.perf_counter()
    if c_specs:
        specs_by_worker_c: List[List[Dict[str, str]]] = [[] for _ in range(thread_count)]
        for idx, spec in enumerate(c_specs):
            specs_by_worker_c[idx % thread_count].append(spec)
        with ThreadPoolExecutor(max_workers=thread_count) as pool:
            futures = [pool.submit(_c_worker, ss) for ss in specs_by_worker_c if ss]
            for fut in futures:
                r = fut.result()
                c_ok += int(r.get("ok_count", 0) or 0)
                c_fail += int(r.get("fail_count", 0) or 0)
                c_failures.extend(r.get("failures") or [])
    _zhr_temp_log_elapsed("normal_update", "refresh_C_from_existing", _t, {"checked": len(c_specs), "ok": c_ok, "fail": c_fail})

    # 更新 last_update_time 为“北京时间 now”
    _t = time.perf_counter()
    _upsert_config_value("last_update_time", now_bj.isoformat())
    _zhr_temp_log_elapsed("normal_update", "update_last_update_time", _t, {"value": now_bj.isoformat()})
    _zhr_temp_log_elapsed("normal_update", "total", _t_all, {"projectId": project_id, "userId": user_id})

    return {
        "success": True,
        "data": {
            "beijing_now": now_bj.isoformat(),
            "last_update_time_before": str(last_raw or ""),
            "incremental_query": {
                "created_gte": created_threshold,
                "created_lte": created_upper,
                "maxResults": max_results,
                "maxPages": max_pages,
            },
            "a_sync": a_out.get("data") or {},
            "incremental_bc": {"count": len(inc_specs), "ok": inc_ok, "fail": inc_fail, "failures": inc_failures[:20]},
            "b_refresh": {
                "window": {"start": start_iso, "end": end_iso},
                "task_count_in_a_window": len(task_specs),
                "b_upserts": b_upserts,
                "b_fail": b_fail,
                "failures": b_failures[:20],
                "thread_count": thread_count,
                "mode": "window-upsert-only",
            },
            "c_refresh": {"checked_from_c": len(c_specs), "ok": c_ok, "fail": c_fail, "failures": c_failures[:20]},
        },
    }
