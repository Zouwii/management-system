"""
将钉钉查询结果落库：A 表列表、B 表明细（模式 1 覆盖）。
"""

from __future__ import annotations

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select, text

from base.db.engine import SessionLocal
from base.db.orm import Config as DbConfig
from base.db.orm import (
    ProgramIssue,
    ProgramIssueDetail,
    ProjectTask,
    ProjectTaskDetail,
    ProjectTaskOverdueDetail,
    SyncFailure,
    UserCharacter as DbUserCharacter,
)
from base.projects.task_service import query_project_tasks_service, query_user_tasks_service
from workhour.personal.util import parse_workhour_from_task_dict
from base.dingtalk_client import get_valid_access_token

DEFAULT_SCENARIO_FIELD_CONFIG_ID = "647854bcd999c893061ef8b5"  # 软件开发
ISSUE_SCENARIO_FIELD_CONFIG_ID = "665ee4b95b46f34b3e0463a8"  # 问题处理
DEFAULT_WORKHOUR_FIELD_ID = "64c8cad8485fb3987a5521b8"
OVERDUE_TAG_ID = "6527846cb6be8066fe331fd0"                   #季度逾期
TASK_NATURE_CUSTOMFIELD_ID = "69d4d037c253ef42e9c31b38"
REQUIREMENT_DESC_CUSTOMFIELD_ID = "686273700d15b3f835491a2e"  #需求描述
TASK_OUTPUT_CUSTOMFIELD_ID = "6862737e3b781c68b3181925"       #任务产出
WORKDAY_DURATION_CUSTOMFIELD_ID = "665ee4b95b46f34b3e04634f"
WORKDAY_FLAG_CUSTOMFIELD_ID = "667a65e618aebd88f98d4896"
NEED_STATISTIC_CUSTOMFIELD_ID = "667a65e618aebd88f98d4896"  # 是/否 标记（与 WORKDAY_FLAG 同一字段）
CASCADING_PROJECT_FIELD_ID = "665ee4b45b46f34b3e045af2"       # 级联：项目分类 / 车型 / 项目名称
PROGRAM_PROBLEM_TYPE_FIELD_ID = "67c56f477ed2b4b7bbd0cd69"
PROGRAM_SOFTWARE_VERSION_FIELD_ID = "65a7be8938685843bf1c7d83"
PROGRAM_CAUSE_FIELD_IDS = {
    "67c571aa5aed540b545e208c",
    "67c571c89a5dc6dbb8511d99",
    "67c5715253aacbf8cf267e81",
    "67c571d86db6f1be2bf2f88f",
}
PROGRAM_VEHICLE_FIELD_ID = "668e05afbe23298626d61027"        # 级联：车型
PROGRAM_NOTE_INFO_FIELD_ID = "67c572129590cd29ac9c5137"      # 级联：问题提示信息
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

from base.sync.lock import (
    acquire_update_lock as _acquire_update_lock,
    get_update_lock_status as _get_update_lock_status,
    release_update_lock as _release_update_lock,
    DEFAULT_UPDATE_LOCK_KEY,
    DEFAULT_UPDATE_LOCK_TTL_SEC,
)

DEFAULT_DB_COMMIT_BATCH_SIZE = 100


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


def _normalize_day_end_utc(dt: datetime) -> datetime:
    d = dt.astimezone(timezone.utc)
    return d.replace(hour=23, minute=59, second=59, microsecond=0)


def _get_config_value(type_: str) -> str:
    sess = SessionLocal()
    try:
        row = sess.query(DbConfig).filter(DbConfig.type_ == str(type_)).first()
        return str(getattr(row, "value", "") or "") if row else ""
    finally:
        sess.close()


def _safe_last_update_time() -> datetime:
    """读取 last_update_time，自动修正异常值。

    保护规则：
    - 缺失/空值 → 回退到 365 天前并写回 DB
    - 早于 365 天前 → 回退到 365 天前并写回 DB
    - 正常值 → 原样返回
    """
    floor = datetime.now(timezone.utc) - timedelta(days=365)
    raw = _get_config_value("last_update_time")
    dt_val = _cmp_dt_utc(_parse_iso_dt(raw)) if raw else None

    if not dt_val or dt_val < floor:
        corrected = floor.isoformat()
        print(f"[safe_last_update_time] corrected: '{raw or '<empty>'}' → {corrected}")
        _upsert_config_value("last_update_time", corrected)
        return floor

    return dt_val


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


def _record_sync_failures(
    *,
    sync_type: str,
    project_id: str,
    phase: str,
    failures: List[Dict[str, Any]],
    retry_round: Optional[int] = None,
) -> None:
    if not failures:
        return
    sess = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        for f in failures:
            task_id = str(f.get("taskId") or "").strip() or None
            executor_id = str(f.get("executorId") or "").strip() or None
            err = str(f.get("error") or "").strip() or None
            meta = dict(f or {})
            sess.add(
                SyncFailure(
                    sync_type=str(sync_type or ""),
                    project_id=str(project_id or "") or None,
                    phase=str(phase or "") or None,
                    task_id=task_id,
                    executor_id=executor_id,
                    retry_round=int(retry_round) if retry_round is not None else None,
                    error_message=err,
                    meta_json=meta,
                    created_at=now,
                )
            )
        sess.commit()
        print(
            "[sync_failures] saved sync_type={} phase={} count={}".format(
                str(sync_type or ""),
                str(phase or ""),
                len(failures),
            )
        )
    except Exception as e:
        sess.rollback()
        print("[sync_failures] save failed:", repr(e))
    finally:
        sess.close()


def _load_allowed_executor_ids() -> set:
    """只允许本体两组 executor；算法组不得进入本体同步链路。"""
    sess = SessionLocal()
    try:
        rows = (
            sess.query(DbUserCharacter.user_id)
            .filter(DbUserCharacter.team_id.in_(("0", "1")))
            .order_by(DbUserCharacter.user_id)
            .all()
        )
        out = {str((r[0] or "")).strip() for r in rows if r and str((r[0] or "")).strip()}
        return out
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


def _extract_task_nature(item: Dict[str, Any]) -> Optional[str]:
    raw = item.get("taskNature")
    if raw is None:
        raw = item.get("task_nature")
    if raw is not None:
        val = str(raw).strip()
        if val:
            return val

    cfs = item.get("customFields") or item.get("customfields") or []
    if not isinstance(cfs, list):
        return None
    for cf in cfs:
        if not isinstance(cf, dict):
            continue
        cfid = str(cf.get("customFieldId") or cf.get("customfieldId") or "").strip()
        if cfid != TASK_NATURE_CUSTOMFIELD_ID:
            continue
        values = cf.get("value") or []
        if isinstance(values, list) and values:
            first = values[0]
            if isinstance(first, dict):
                # 优先存 customFieldValueId，前端已有映射逻辑；无则退化标题
                v = str(first.get("customFieldValueId") or "").strip()
                if v:
                    return v
                t = str(first.get("title") or "").strip()
                if t:
                    return t
        break
    return None



def _custom_fields_list(item_or_fields: Any) -> List[Dict[str, Any]]:
    if isinstance(item_or_fields, list):
        return [cf for cf in item_or_fields if isinstance(cf, dict)]
    if isinstance(item_or_fields, dict):
        fields = item_or_fields.get("customFields") or item_or_fields.get("customfields") or []
        if isinstance(fields, list):
            return [cf for cf in fields if isinstance(cf, dict)]
    return []


def _extract_custom_field_value_titles(item_or_fields: Any, custom_field_id: str) -> List[str]:
    out: List[str] = []
    for cf in _custom_fields_list(item_or_fields):
        cfid = str(cf.get("customFieldId") or cf.get("customfieldId") or "").strip()
        if cfid != str(custom_field_id):
            continue
        values = cf.get("value")
        nodes: List[Any]
        if isinstance(values, list):
            nodes = values
        elif values is None:
            nodes = []
        else:
            nodes = [values]
        for node in nodes:
            if isinstance(node, dict):
                title = str(
                    node.get("title")
                    or node.get("value")
                    or node.get("metaString")
                    or node.get("text")
                    or node.get("customFieldValueId")
                    or ""
                ).strip()
            else:
                title = str(node or "").strip()
            if title:
                out.append(title)
        break
    return out


def _extract_requirement_desc(item_or_fields: Any) -> str:
    titles = _extract_custom_field_value_titles(item_or_fields, REQUIREMENT_DESC_CUSTOMFIELD_ID)
    return titles[0] if titles else ""


def _extract_task_outputs(item_or_fields: Any) -> List[str]:
    return _extract_custom_field_value_titles(item_or_fields, TASK_OUTPUT_CUSTOMFIELD_ID)


def _serialize_outputs(outputs: List[str]) -> str:
    return "\n".join(outputs) if outputs else ""


def _extract_workday_costhour(item: Dict[str, Any]) -> Optional[float]:
    # 优先直接字段；语义：None=未填，0=否，>0=是
    direct = None
    if isinstance(item, dict):
        direct = item.get("workday_costhour")
    if direct is not None:
        try:
            return float(direct)
        except (TypeError, ValueError):
            pass

    cfs = item.get("customFields") or item.get("customfields") or []
    if not isinstance(cfs, list):
        return None
    num_candidate: Optional[float] = None
    flag_candidate: Optional[int] = None
    for cf in cfs:
        if not isinstance(cf, dict):
            continue
        cfid = str(cf.get("customFieldId") or cf.get("customfieldId") or "").strip()
        if cfid not in {
            WORKDAY_DURATION_CUSTOMFIELD_ID,
            WORKDAY_FLAG_CUSTOMFIELD_ID,
            "workday_costhour",
        }:
            continue
        value = cf.get("value")
        if isinstance(value, list) and value:
            node = value[0]
            if isinstance(node, dict):
                candidate = (
                    node.get("value")
                    if node.get("value") is not None
                    else node.get("title")
                )
            else:
                candidate = node
        else:
            candidate = value
        if cfid == WORKDAY_FLAG_CUSTOMFIELD_ID:
            txt = str(candidate or "").strip()
            if txt in {"否", "No", "no", "false", "False", "0"}:
                flag_candidate = 0
            elif txt in {"是", "Yes", "yes", "true", "True", "1"}:
                # 仅标记“有”，具体分钟数优先使用数值字段
                flag_candidate = 1
            continue
        try:
            num_candidate = float(candidate)
        except (TypeError, ValueError):
            continue
    if num_candidate is not None:
        return num_candidate
    if flag_candidate is not None:
        # 严格口径：否=0；是但无数值=NULL（由前端按空值展示）
        return 0 if flag_candidate == 0 else None
    return None


def _extract_cascading_project_fields(item: Dict[str, Any]) -> Dict[str, Optional[str]]:
    """
    从 customFields 中一次遍历同时解析：
      - CASCADING_PROJECT_FIELD_ID → project_catagory_1/2/3（新名）+ 旧名兼容

    Teambition 数据格式:
      {
        "customFieldId": "665ee4b45b46f34b3e045af2",
        "type": "cascading",
        "value": [
          { "title": "产品项目 / 通用 / 出厂流程优化" }
        ]
      }

    返回: {
        project_catagory_1: str|None,    project_catagory_2: str|None,    project_catagory_3: str|None,
        project_category_1: str|None,     vehicle_type_2: str|None,        project_name_3: str|None,   (兼容)
        need_statistic: str|None,
    }
    """
    result = {
        "project_catagory_1": None,
        "project_catagory_2": None,
        "project_catagory_3": None,
        # ── 兼容旧名 ──
        "project_category_1": None,
        "vehicle_type_2": None,
        "project_name_3": None,
        # ── 其他 ──
        "need_statistic": None,
    }
    cfs = item.get("customFields") or item.get("customfields") or []
    if not isinstance(cfs, list):
        return result

    for cf in cfs:
        if not isinstance(cf, dict):
            continue
        cfid = str(cf.get("customFieldId") or cf.get("customfieldId") or "").strip()

        # ── 级联字段：项目分类 ──
        if cfid == CASCADING_PROJECT_FIELD_ID:
            values = cf.get("value") or []
            if isinstance(values, list) and values:
                first = values[0]
                if isinstance(first, dict):
                    title = str(first.get("title") or "").strip()
                    if title:
                        parts = [p.strip() for p in title.split("/")]
                        if len(parts) >= 1 and parts[0]:
                            result["project_catagory_1"] = parts[0]
                            result["project_category_1"] = parts[0]   # 兼容旧名
                        if len(parts) >= 2 and parts[1]:
                            result["project_catagory_2"] = parts[1]
                            result["vehicle_type_2"] = parts[1]       # 兼容旧名
                        if len(parts) >= 3 and parts[2]:
                            result["project_catagory_3"] = parts[2]
                            result["project_name_3"] = parts[2]       # 兼容旧名

        # ── 是否计入统计（与 WORKDAY_FLAG 同一字段）──
        elif cfid == NEED_STATISTIC_CUSTOMFIELD_ID:
            values = cf.get("value") or []
            if isinstance(values, list) and values:
                first = values[0]
                if isinstance(first, dict):
                    title = str(first.get("title") or "").strip()
                    if title in ("是", "否"):
                        result["need_statistic"] = title

    return result


def _extract_program_issue_label_levels(item: Dict[str, Any]) -> Dict[str, Optional[str]]:
    """解析问题类型、问题原因、车型、问题提示信息的层级标签。"""
    result = {
        "problem_type_1": None,
        "problem_type_2": None,
        "cause_level_1": None,
        "cause_level_2": None,
        "cause_level_3": None,
        "vehicle_1": None,
        "vehicle_2": None,
        "problem_note_info_1": None,
        "problem_note_info_2": None,
        "problem_note_info_3": None,
    }
    cfs = item.get("customFields") or item.get("customfields") or []
    if not isinstance(cfs, list):
        return result

    problem_type_ids = {PROGRAM_PROBLEM_TYPE_FIELD_ID}
    cause_paths = []
    for cf in cfs:
        if not isinstance(cf, dict):
            continue
        cfid = str(cf.get("customFieldId") or cf.get("customfieldId") or "").strip()

        # ── 问题类型 ──
        if cfid in problem_type_ids:
            for value in cf.get("value") or []:
                if not isinstance(value, dict) or not value.get("title"):
                    continue
                parts = [part.strip() for part in str(value["title"]).split("/") if part.strip()]
                for index, part in enumerate(parts[:2], 1):
                    key = f"problem_type_{index}"
                    if result[key] is None:
                        result[key] = part
                    elif part not in result[key].split("; "):
                        result[key] += f"; {part}"
            continue

        # ── 问题原因 ──
        if cfid in PROGRAM_CAUSE_FIELD_IDS:
            for value in cf.get("value") or []:
                if isinstance(value, dict) and value.get("title"):
                    parts = [part.strip() for part in str(value["title"]).split("/") if part.strip()]
                    if parts:
                        cause_paths.append(parts[:3])
            continue

        # ── 车型 ──
        if cfid == PROGRAM_VEHICLE_FIELD_ID:
            for value in cf.get("value") or []:
                if not isinstance(value, dict) or not value.get("title"):
                    continue
                parts = [part.strip() for part in str(value["title"]).split("/") if part.strip()]
                for index, part in enumerate(parts[:2], 1):
                    key = f"vehicle_{index}"
                    result[key] = part
            continue

        # ── 问题提示信息 ──
        if cfid == PROGRAM_NOTE_INFO_FIELD_ID:
            for value in cf.get("value") or []:
                if not isinstance(value, dict) or not value.get("title"):
                    continue
                parts = [part.strip() for part in str(value["title"]).split("/") if part.strip()]
                for index, part in enumerate(parts[:3], 1):
                    key = f"problem_note_info_{index}"
                    result[key] = part
            continue

    if cause_paths:
        best = max(cause_paths, key=len)
        for index, part in enumerate(best, 1):
            result[f"cause_level_{index}"] = part
    return result


def _extract_program_issue_software_version(item: Dict[str, Any]) -> Optional[str]:
    cfs = item.get("customFields") or item.get("customfields") or []
    if not isinstance(cfs, list):
        return None
    titles = []
    for cf in cfs:
        if not isinstance(cf, dict):
            continue
        cfid = str(cf.get("customFieldId") or cf.get("customfieldId") or "").strip()
        if cfid != PROGRAM_SOFTWARE_VERSION_FIELD_ID:
            continue
        for value in cf.get("value") or []:
            if isinstance(value, dict) and value.get("title"):
                title = str(value["title"]).strip()
                if title and title not in titles:
                    titles.append(title)
    return "; ".join(titles) if titles else None


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
    scenario_id = str(item.get("scenarioFieldConfigId") or item.get("scenariofieldconfigId") or "")
    content = str(item.get("content") or "")
    due_date = _parse_iso_dt(item.get("dueDate"))
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
    parent_id = str(item.get("parentTaskId") or item.get("parent_id") or "") or None
    task_nature = _extract_task_nature(item)
    workday_costhour = _extract_workday_costhour(item)
    cascading = _extract_cascading_project_fields(item)
    label_levels = _extract_program_issue_label_levels(item)
    software_version = _extract_program_issue_software_version(item)

    if write_b:
        if is_overdue:
            # 逾期任务不应留在 B 表，删掉
            stmt_del = select(ProjectTaskDetail).where(
                ProjectTaskDetail.task_id == task_id,
                ProjectTaskDetail.query_user_id == executor_id,
            )
            row_del = one_session.scalars(stmt_del).first()
            if row_del:
                one_session.delete(row_del)
        else:
            stmt = select(ProjectTaskDetail).where(
                ProjectTaskDetail.task_id == task_id,
                ProjectTaskDetail.query_user_id == executor_id,
            )
            row = one_session.scalars(stmt).first()
            if row:
                row.project_id = project_id
                row.scenario_field_config_id = scenario_id or DEFAULT_SCENARIO_FIELD_CONFIG_ID
                row.content = content
                row.due_date = due_date
                row.work_hour_field_id = field_id
                row.work_hour = wh
                row.custom_fields_json = cfs if cfs is not None else None
                row.raw_json = raw_blob
                row.parent_task_id = parent_id
                row.parent_id = parent_id
                row.task_list_id = str(item.get("taskListId") or "") or None
                row.task_stage_id = str(item.get("taskStageId") or item.get("stageId") or "") or None
                row.unique_id = unique_id
                row.task_nature = task_nature
                row.need_statistic = cascading["need_statistic"]
                row.workday_costhour = workday_costhour
                row.requirement_desc = _extract_requirement_desc(item)
                row.task_outputs = _serialize_outputs(_extract_task_outputs(item))
                row.is_overdue = is_overdue
                row.business_type = business_type
                row.task_flow_status_id = task_flow_status_id
                row.project_category_1 = cascading["project_category_1"]
                row.vehicle_type_2 = cascading["vehicle_type_2"]
                row.project_name_3 = cascading["project_name_3"]
                row.fetched_at = now
            else:
                one_session.add(
                    ProjectTaskDetail(
                        project_id=project_id,
                        task_id=task_id,
                        query_user_id=executor_id,
                        scenario_field_config_id=scenario_id or DEFAULT_SCENARIO_FIELD_CONFIG_ID,
                        content=content,
                        due_date=due_date,
                        work_hour_field_id=field_id,
                        work_hour=wh,
                        custom_fields_json=cfs if cfs is not None else None,
                        raw_json=raw_blob,
                        parent_task_id=parent_id,
                        parent_id=parent_id,
                        task_list_id=str(item.get("taskListId") or "") or None,
                        task_stage_id=str(item.get("taskStageId") or item.get("stageId") or "") or None,
                        unique_id=unique_id,
                        task_nature=task_nature,
                        need_statistic=cascading["need_statistic"],
                        workday_costhour=workday_costhour,
                        requirement_desc=_extract_requirement_desc(item),
                        task_outputs=_serialize_outputs(_extract_task_outputs(item)),
                        is_overdue=is_overdue,
                        business_type=business_type,
                        task_flow_status_id=task_flow_status_id,
                        project_category_1=cascading["project_category_1"],
                        vehicle_type_2=cascading["vehicle_type_2"],
                        project_name_3=cascading["project_name_3"],
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
                row2.scenario_field_config_id = scenario_id or DEFAULT_SCENARIO_FIELD_CONFIG_ID
                row2.content = content
                row2.due_date = due_date
                row2.work_hour = wh
                row2.business_type = business_type
                row2.task_flow_status_id = task_flow_status_id
                row2.parent_id = parent_id
                row2.task_nature = task_nature
                row2.need_statistic = cascading["need_statistic"]
                row2.workday_costhour = workday_costhour
                row2.custom_fields_json = cfs if cfs is not None else None
                row2.raw_json = raw_blob
                row2.project_category_1 = cascading["project_category_1"]
                row2.vehicle_type_2 = cascading["vehicle_type_2"]
                row2.project_name_3 = cascading["project_name_3"]
                row2.fetched_at = now
            else:
                one_session.add(
                    ProjectTaskOverdueDetail(
                        project_id=project_id,
                        task_id=task_id,
                        query_user_id=executor_id,
                        scenario_field_config_id=scenario_id or DEFAULT_SCENARIO_FIELD_CONFIG_ID,
                        content=content,
                        due_date=due_date,
                        work_hour=wh,
                        business_type=business_type,
                        task_flow_status_id=task_flow_status_id,
                        parent_id=parent_id,
                        task_nature=task_nature,
                        need_statistic=cascading["need_statistic"],
                        workday_costhour=workday_costhour,
                        custom_fields_json=cfs if cfs is not None else None,
                        raw_json=raw_blob,
                        project_category_1=cascading["project_category_1"],
                        vehicle_type_2=cascading["vehicle_type_2"],
                        project_name_3=cascading["project_name_3"],
                        fetched_at=now,
                    )
                )
        else:
            # 逾期标签可能被去掉：保持 C 为“当前逾期快照”，若存在则删掉
            if row2:
                one_session.delete(row2)

    return {"work_hour": wh, "is_overdue": is_overdue}


def _sync_one_issue_detail(
    one_session,
    *,
    executor_id: str,
    task_id: str,
    project_id: str,
    item: Dict[str, Any],
    field_id: str,
    now: datetime,
    business_type_mapping: Dict[str, int],
) -> Dict[str, Any]:
    tag_ids = item.get("tagIds") or item.get("tagids") or []
    business_type = _resolve_business_type_from_tags(
        [str(x) for x in tag_ids] if isinstance(tag_ids, list) else [],
        business_type_mapping,
    )
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

    scenario_id = str(item.get("scenarioFieldConfigId") or item.get("scenariofieldconfigId") or "")
    parent_id = str(item.get("parentTaskId") or item.get("parent_id") or "") or None
    task_nature = _extract_task_nature(item)
    workday_costhour = _extract_workday_costhour(item)
    cascading = _extract_cascading_project_fields(item)
    label_levels = _extract_program_issue_label_levels(item)
    software_version = _extract_program_issue_software_version(item)
    stmt = select(ProgramIssueDetail).where(
        ProgramIssueDetail.task_id == task_id,
        ProgramIssueDetail.query_user_id == executor_id,
    )
    row = one_session.scalars(stmt).first()
    if row:
        row.project_id = project_id
        row.scenario_field_config_id = scenario_id or ISSUE_SCENARIO_FIELD_CONFIG_ID
        row.content = str(item.get("content") or "")
        row.executor_id = str(item.get("executorId") or "")
        row.creator_id = str(item.get("creatorId") or "")
        row.task_list_id = str(item.get("taskListId") or "") or None
        row.task_stage_id = str(item.get("taskStageId") or item.get("stageId") or "") or None
        row.taskflow_status_id = str(item.get("taskflowStatusId") or item.get("taskflowstatusId") or "") or None
        row.unique_id = unique_id
        row.parent_id = parent_id
        row.task_nature = task_nature
        row.need_statistic = cascading["need_statistic"]
        row.workday_costhour = workday_costhour
        row.work_hour_field_id = field_id
        row.work_hour = wh
        row.business_type = business_type
        row.is_archived = bool(item.get("isArchived"))
        row.is_done = bool(item.get("isDone"))
        row.priority = int(item.get("priority")) if item.get("priority") is not None else None
        row.visible = str(item.get("visible") or "") or None
        row.created_at_ding = _parse_iso_dt(item.get("created"))
        row.updated_at_ding = _parse_iso_dt(item.get("updated"))
        row.ancestor_ids = _str_list("ancestorIds", item) or None
        row.involve_members = _str_list("involveMembers", item) or None
        row.tag_ids = [str(x) for x in tag_ids] if isinstance(tag_ids, list) else None
        row.custom_fields_json = cfs if cfs is not None else None
        row.raw_json = raw_blob
        row.project_catagory_1 = cascading["project_catagory_1"]
        row.project_catagory_2 = cascading["project_catagory_2"]
        row.project_catagory_3 = cascading["project_catagory_3"]
        for key, value in label_levels.items():
            setattr(row, key, value)
        row.software_version = software_version
        row.fetched_at = now
    else:
        one_session.add(
            ProgramIssueDetail(
                project_id=project_id,
                task_id=task_id,
                query_user_id=executor_id,
                scenario_field_config_id=scenario_id or ISSUE_SCENARIO_FIELD_CONFIG_ID,
                content=str(item.get("content") or ""),
                executor_id=str(item.get("executorId") or ""),
                creator_id=str(item.get("creatorId") or ""),
                task_list_id=str(item.get("taskListId") or "") or None,
                task_stage_id=str(item.get("taskStageId") or item.get("stageId") or "") or None,
                taskflow_status_id=str(item.get("taskflowStatusId") or item.get("taskflowstatusId") or "") or None,
                unique_id=unique_id,
                parent_id=parent_id,
                task_nature=task_nature,
                need_statistic=cascading["need_statistic"],
                workday_costhour=workday_costhour,
                work_hour_field_id=field_id,
                work_hour=wh,
                business_type=business_type,
                is_archived=bool(item.get("isArchived")),
                is_done=bool(item.get("isDone")),
                priority=int(item.get("priority")) if item.get("priority") is not None else None,
                visible=str(item.get("visible") or "") or None,
                created_at_ding=_parse_iso_dt(item.get("created")),
                updated_at_ding=_parse_iso_dt(item.get("updated")),
                ancestor_ids=_str_list("ancestorIds", item) or None,
                involve_members=_str_list("involveMembers", item) or None,
                tag_ids=[str(x) for x in tag_ids] if isinstance(tag_ids, list) else None,
                custom_fields_json=cfs if cfs is not None else None,
                raw_json=raw_blob,
                project_catagory_1=cascading["project_catagory_1"],
                project_catagory_2=cascading["project_catagory_2"],
                project_catagory_3=cascading["project_catagory_3"],
                problem_type_1=label_levels["problem_type_1"],
                problem_type_2=label_levels["problem_type_2"],
                vehicle_1=label_levels["vehicle_1"],
                vehicle_2=label_levels["vehicle_2"],
                problem_note_info_1=label_levels["problem_note_info_1"],
                problem_note_info_2=label_levels["problem_note_info_2"],
                problem_note_info_3=label_levels["problem_note_info_3"],
                cause_level_1=label_levels["cause_level_1"],
                cause_level_2=label_levels["cause_level_2"],
                cause_level_3=label_levels["cause_level_3"],
                software_version=software_version,
                fetched_at=now,
            )
        )
    return {"work_hour": wh}


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


def _apply_task_dict_to_orm(obj: Any, d: Dict[str, Any], list_synced_at: datetime) -> None:
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


def _normalize_scenario_ids(payload: Dict[str, Any]) -> List[str]:
    sid_single = str(
        payload.get("scenarioFieldConfigId")
        or payload.get("scenarioFieldConfigID")
        or ""
    ).strip()
    sid_list = payload.get("scenarioFieldConfigIds")
    out: List[str] = []
    if isinstance(sid_list, list):
        for sid in sid_list:
            s = str(sid or "").strip()
            if s:
                out.append(s)
    elif isinstance(sid_list, str) and sid_list.strip():
        out.extend([x.strip() for x in sid_list.split(",") if str(x).strip()])
    if sid_single:
        out.append(sid_single)
    if not out:
        out = [DEFAULT_SCENARIO_FIELD_CONFIG_ID]
    # preserve order while dedup
    dedup: List[str] = []
    seen = set()
    for x in out:
        if x in seen:
            continue
        seen.add(x)
        dedup.append(x)
    return dedup


def _upsert_filtered_project_tasks(
    payload: Dict[str, Any], query_result: Dict[str, Any]
) -> Dict[str, Any]:
    """
    从已成功返回的 query_project_tasks_service 结果中按 scenario 过滤并 upsert A 表。
    """
    scenario_ids = _normalize_scenario_ids(payload)

    ding = (query_result.get("data") or {}).get("dingtalk") or {}
    all_rows = ding.get("result") if isinstance(ding.get("result"), list) else []
    filtered: List[Dict[str, Any]] = []
    for r in all_rows:
        if not isinstance(r, dict):
            continue
        sid = str(r.get("scenariofieldconfigId") or r.get("scenarioFieldConfigId") or "")
        if sid in scenario_ids:
            filtered.append(r)

    now = datetime.now(timezone.utc)
    session = SessionLocal()
    upserted = 0
    upserted_dev = 0
    upserted_issue = 0
    try:
        for d in filtered:
            pid = str(d.get("projectId") or "")
            tid = str(d.get("taskId") or "")
            sid = str(d.get("scenariofieldconfigId") or d.get("scenarioFieldConfigId") or "")
            if not pid or not tid:
                continue
            if sid == ISSUE_SCENARIO_FIELD_CONFIG_ID:
                stmt = select(ProgramIssue).where(
                    ProgramIssue.project_id == pid,
                    ProgramIssue.task_id == tid,
                )
                existing = session.scalars(stmt).first()
                if existing:
                    _apply_task_dict_to_orm(existing, d, now)
                else:
                    row = ProgramIssue()
                    _apply_task_dict_to_orm(row, d, now)
                    session.add(row)
                upserted_issue += 1
            else:
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
                upserted_dev += 1
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
            "upserted_dev": upserted_dev,
            "upserted_issue": upserted_issue,
            "filtered_count": len(filtered),
            "fetched_count": len(all_rows),
            "scenario_field_config_ids": scenario_ids,
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
    scenario_id = str(item.get("scenarioFieldConfigId") or item.get("scenariofieldconfigId") or "")
    content = str(item.get("content") or "")
    due_date = _parse_iso_dt(item.get("dueDate"))
    try:
        casc = _extract_cascading_project_fields(item)
        stmt = select(ProjectTaskDetail).where(
            ProjectTaskDetail.task_id == task_id,
            ProjectTaskDetail.query_user_id == user_id,
        )
        row = session.scalars(stmt).first()
        if row:
            row.project_id = project_id
            row.scenario_field_config_id = scenario_id or DEFAULT_SCENARIO_FIELD_CONFIG_ID
            row.content = content
            row.due_date = due_date
            row.work_hour_field_id = field_id
            row.work_hour = wh
            row.custom_fields_json = cfs if cfs is not None else None
            row.raw_json = raw_blob
            parent_id = str(item.get("parentTaskId") or item.get("parent_id") or "") or None
            row.parent_task_id = parent_id
            row.parent_id = parent_id
            row.task_list_id = str(item.get("taskListId") or "") or None
            row.task_stage_id = str(item.get("taskStageId") or item.get("stageId") or "") or None
            row.unique_id = unique_id
            row.task_nature = _extract_task_nature(item)
            row.need_statistic = casc["need_statistic"]
            row.is_overdue = is_overdue
            row.business_type = business_type
            row.task_flow_status_id = task_flow_status_id
            row.project_category_1 = casc["project_category_1"]
            row.vehicle_type_2 = casc["vehicle_type_2"]
            row.project_name_3 = casc["project_name_3"]
            row.fetched_at = now
        else:
            session.add(
                ProjectTaskDetail(
                    project_id=project_id,
                    task_id=task_id,
                    query_user_id=user_id,
                    scenario_field_config_id=scenario_id or DEFAULT_SCENARIO_FIELD_CONFIG_ID,
                    content=content,
                    due_date=due_date,
                    work_hour_field_id=field_id,
                    work_hour=wh,
                    custom_fields_json=cfs if cfs is not None else None,
                    raw_json=raw_blob,
                    parent_task_id=str(item.get("parentTaskId") or item.get("parent_id") or "") or None,
                    parent_id=str(item.get("parentTaskId") or item.get("parent_id") or "") or None,
                    task_list_id=str(item.get("taskListId") or "") or None,
                    task_stage_id=str(item.get("taskStageId") or item.get("stageId") or "") or None,
                    unique_id=unique_id,
                    task_nature=_extract_task_nature(item),
                    need_statistic=casc["need_statistic"],
                    requirement_desc=_extract_requirement_desc(item),
                    task_outputs=_serialize_outputs(_extract_task_outputs(item)),
                    is_overdue=is_overdue,
                    business_type=business_type,
                    task_flow_status_id=task_flow_status_id,
                    project_category_1=casc["project_category_1"],
                    vehicle_type_2=casc["vehicle_type_2"],
                    project_name_3=casc["project_name_3"],
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
    增量更新：从 last_update_time 至今的变更。
    1) 读取 config.last_update_time 作为窗口起点（如无记录则用今天-1天）
    2) 调钉钉 API 拉 updated >= last_update_time 的任务列表
    3) 按 scenario=软件开发 过滤后 upsert 到 A 表
    4) 同步详情到 B 表
    5) 完成后更新 last_update_time

    注意：该接口不负责更新 C 表（overdue），全量更新才会更新 C。
    """

    payload = dict(payload or {})
    user_id = str(payload.get("userId") or payload.get("userid") or "").strip()
    project_id = str(payload.get("projectId") or payload.get("projectid") or "").strip()
    if not user_id or not project_id:
        return {"success": False, "error": "missing userId or projectId", "data": {}}

    # 增量起点：读 last_update_time（自动修正异常值）
    last_update_dt = _safe_last_update_time()

    # 窗口终点：用前端传的 endDate，或回退到今天
    end_dt = _parse_iso_dt(payload.get("endDate") or payload.get("end_time") or payload.get("endTime"))
    if not end_dt:
        end_dt = datetime.now(timezone.utc)
    end_dt = _cmp_dt_utc(end_dt)

    # 也保留 due_date 窗口（用于 A 表过滤），用前端传的 startDate 或 last_update_time 前一年
    start_dt = _parse_iso_dt(payload.get("startDate") or payload.get("start_time") or payload.get("startTime"))
    if not start_dt:
        start_dt = last_update_dt - timedelta(days=365)
    start_dt = _cmp_dt_utc(start_dt)

    def _format_dt_for_tql(dt: datetime) -> str:
        d = dt.astimezone(timezone.utc).replace(microsecond=0)
        return d.strftime("%Y-%m-%dT%H:%M:%S") + ".000Z"

    # 增量查询：只拉 updated >= last_update_time 且有 due_date 窗口的
    query = (
        "(dueDate >= '{start}') AND (dueDate <= '{end}')"
        " AND (updated >= '{updated_after}')"
    ).format(
        start=_format_dt_for_tql(start_dt),
        end=_format_dt_for_tql(end_dt),
        updated_after=_format_dt_for_tql(last_update_dt),
    )

    print(
        "[time_range_update] incremental: updated_after={} start={} end={}".format(
            _format_dt_for_tql(last_update_dt),
            _format_dt_for_tql(start_dt),
            _format_dt_for_tql(end_dt),
        )
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

    allowed_executor_ids = _load_allowed_executor_ids()
    session = SessionLocal()
    task_specs: List[Dict[str, str]] = []
    skipped_by_character = 0
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
            if allowed_executor_ids and executor_id not in allowed_executor_ids:
                skipped_by_character += 1
                continue
            task_specs.append({"task_id": task_id, "executor_id": executor_id, "project_id": project_id})
    finally:
        session.close()
    if skipped_by_character > 0:
        print(
            "[time_range_update] skipped_by_character={} (executor not in user_character)".format(
                skipped_by_character
            )
        )

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
                casc = _extract_cascading_project_fields(item)
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
                    parent_id = str(item.get("parentTaskId") or item.get("parent_id") or "") or None
                    row.parent_task_id = parent_id
                    row.parent_id = parent_id
                    row.task_list_id = str(item.get("taskListId") or "") or None
                    row.task_stage_id = str(item.get("taskStageId") or item.get("stageId") or "") or None
                    row.unique_id = unique_id
                    row.task_nature = _extract_task_nature(item)
                    row.need_statistic = casc["need_statistic"]
                    row.workday_costhour = _extract_workday_costhour(item)
                    row.is_overdue = is_overdue
                    row.business_type = business_type
                    row.task_flow_status_id = task_flow_status_id
                    row.project_category_1 = casc["project_category_1"]
                    row.vehicle_type_2 = casc["vehicle_type_2"]
                    row.project_name_3 = casc["project_name_3"]
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
                            parent_task_id=str(item.get("parentTaskId") or item.get("parent_id") or "") or None,
                            parent_id=str(item.get("parentTaskId") or item.get("parent_id") or "") or None,
                            task_list_id=str(item.get("taskListId") or "") or None,
                            task_stage_id=str(item.get("taskStageId") or item.get("stageId") or "") or None,
                            unique_id=unique_id,
                            task_nature=_extract_task_nature(item),
                            need_statistic=casc["need_statistic"],
                            workday_costhour=_extract_workday_costhour(item),
                            is_overdue=is_overdue,
                            business_type=business_type,
                            task_flow_status_id=task_flow_status_id,
                            project_category_1=casc["project_category_1"],
                            vehicle_type_2=casc["vehicle_type_2"],
                            project_name_3=casc["project_name_3"],
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
    b_fail_initial = b_fail
    b_retry_attempted = 0
    b_retry_recovered = 0
    max_retry_rounds = 5
    if b_failures:
        spec_by_key: Dict[tuple, Dict[str, str]] = {
            (str(s.get("task_id") or ""), str(s.get("executor_id") or "")): s for s in task_specs
        }
        retry_round = 0
        while b_failures and retry_round < max_retry_rounds:
            retry_round += 1
            retry_specs: List[Dict[str, str]] = []
            seen_retry = set()
            for f in b_failures:
                key = (str(f.get("taskId") or ""), str(f.get("executorId") or ""))
                if key in seen_retry:
                    continue
                seen_retry.add(key)
                sp = spec_by_key.get(key)
                if sp:
                    retry_specs.append(sp)
            if not retry_specs:
                break
            b_retry_attempted += len(retry_specs)
            print(
                "[time_range_update][b_retry] round={}/{} attempt={} remain_before={}".format(
                    retry_round,
                    max_retry_rounds,
                    len(retry_specs),
                    len(b_failures),
                )
            )
            retry_slices: List[List[Dict[str, str]]] = [[] for _ in range(thread_count)]
            for idx, spec in enumerate(retry_specs):
                retry_slices[idx % thread_count].append(spec)
            retry_failures: List[Dict[str, Any]] = []
            with ThreadPoolExecutor(max_workers=thread_count) as retry_pool:
                retry_futures = [retry_pool.submit(_worker, ss) for ss in retry_slices if ss]
                for fut in retry_futures:
                    rr = fut.result()
                    b_upserts += int(rr.get("ok_upserts", 0) or 0)
                    retry_failures.extend(rr.get("failures") or [])
            b_failures = retry_failures
            print(
                "[time_range_update][b_retry] round={}/{} remain_after={}".format(
                    retry_round,
                    max_retry_rounds,
                    len(b_failures),
                )
            )
        b_fail = len(b_failures)
        b_retry_recovered = max(b_fail_initial - b_fail, 0)
    _record_sync_failures(
        sync_type="time_range_update",
        project_id=project_id,
        phase="b_sync",
        failures=b_failures,
        retry_round=max_retry_rounds if b_failures else None,
    )

    # 增量更新完成后刷新 last_update_time
    from base.config.service import touch_last_update_time_service
    touch_last_update_time_service()

    return {
        "success": True,
        "data": {
            "query": query,
            "a_sync": sync_out.get("data") or {},
            "b_sync": {
                "task_count_in_a": len(task_specs),
                "skipped_by_character": skipped_by_character,
                "b_upserts": b_upserts,
                "b_fail": b_fail,
                "b_fail_initial": b_fail_initial,
                "b_retry_attempted": b_retry_attempted,
                "b_retry_recovered": b_retry_recovered,
                "failures": b_failures[:20],
                "mode": "upsert-cleanup",
            },
        },
    }


def normal_incremental_update_service(payload: Dict[str, Any], skip_update_time: bool = False) -> Dict[str, Any]:
    """
    普通更新（按钮专用）：
    1) 增量窗口：last_update_time → 现在（无上界）
    2) 对增量结果写入 A，并对变更任务写入 B/C
       （_sync_one_detail_to_b_and_c 已覆盖：新增/内容变更→B，逾期状态变更→C增删）
    """
    payload = dict(payload or {})
    user_id = str(payload.get("userId") or payload.get("userid") or "").strip()
    project_id = str(payload.get("projectId") or payload.get("projectid") or "").strip()
    if not user_id or not project_id:
        return {"success": False, "error": "missing userId or projectId", "data": {}}

    # 1) 读取 last_update_time（自动修正异常值）
    from base.api_monitor import BJ_TZ
    now_bj = datetime.now(BJ_TZ)
    last_dt = _safe_last_update_time()
    last_raw = _format_dt_for_tql_utc(last_dt)
    updated_threshold = _format_dt_for_tql_utc(last_dt)

    max_results = int(payload.get("maxResults", 500) or 500)
    max_pages = int(payload.get("maxPages", 200) or 200)

    # 3) 钉钉增量拉列表：updated >= last_update_time（无上界）
    inc_payload = dict(payload)
    inc_payload.update(
        {
            "userId": user_id,
            "projectId": project_id,
            "query": "(updated >= '{t0}')".format(t0=updated_threshold),
            "maxResults": max_results,
            "maxPages": max_pages,
            "force_refresh": True,
        }
    )
    inc_res = query_project_tasks_service(inc_payload)
    if not inc_res.get("success"):
        return {"success": False, "error": inc_res.get("error", "incremental query failed"), "data": inc_res}

    # 4) 写 A；并对增量结果的任务写 B/C
    a_out = sync_project_tasks_to_db(inc_payload, query_result=inc_res)
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

    allowed_executor_ids = _load_allowed_executor_ids()
    ding = (inc_res.get("data") or {}).get("dingtalk") or {}
    all_rows = ding.get("result") if isinstance(ding.get("result"), list) else []
    scenario_id = str(payload.get("scenarioFieldConfigId") or DEFAULT_SCENARIO_FIELD_CONFIG_ID)
    inc_specs: List[Dict[str, str]] = []
    inc_skipped_by_character = 0
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
        if allowed_executor_ids and ex not in allowed_executor_ids:
            inc_skipped_by_character += 1
            continue
        inc_specs.append({"task_id": tid, "executor_id": ex, "project_id": project_id})

    inc_ok = 0
    inc_fail = 0
    inc_failures: List[Dict[str, Any]] = []
    if inc_specs:
        sess = SessionLocal()
        pending_commit = 0
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
                pending_commit += 1
                if pending_commit >= DEFAULT_DB_COMMIT_BATCH_SIZE:
                    sess.commit()
                    pending_commit = 0
                inc_ok += 1
            if pending_commit > 0:
                sess.commit()
        finally:
            sess.close()
    _record_sync_failures(
        sync_type="normal_update",
        project_id=project_id,
        phase="incremental_bc",
        failures=inc_failures,
        retry_round=None,
    )

    # 更新 last_update_time 为"北京时间 now"
    if not skip_update_time:
        _upsert_config_value("last_update_time", now_bj.isoformat())
    print(
        "[normal_update] success projectId={} userId={} inc_count={}".format(
            project_id,
            user_id,
            len(inc_specs),
        )
    )

    return {
        "success": True,
        "data": {
            "beijing_now": now_bj.isoformat(),
            "last_update_time_before": str(last_raw or ""),
            "incremental_query": {
                "updated_gte": updated_threshold,
                "maxResults": max_results,
                "maxPages": max_pages,
            },
            "a_sync": a_out.get("data") or {},
            "incremental_bc": {"count": len(inc_specs), "ok": inc_ok, "fail": inc_fail, "failures": inc_failures[:20]},
            "character_filter": {
                "incremental_skipped_by_character": inc_skipped_by_character,
            },
        },
    }


def normal_issue_incremental_update_service(payload: Dict[str, Any], skip_update_time: bool = False) -> Dict[str, Any]:
    """
    Program Issue 增量更新：
    1) 增量窗口：last_update_time → 现在（无上界）
    2) 对增量结果写入 ProgramIssue A 表，并对变更任务写入 ProgramIssueDetail
    """
    payload = dict(payload or {})
    user_id = str(payload.get("userId") or payload.get("userid") or "").strip()
    project_id = str(payload.get("projectId") or payload.get("projectid") or "").strip()
    if not user_id or not project_id:
        return {"success": False, "error": "missing userId or projectId", "data": {}}

    from base.api_monitor import BJ_TZ
    now_bj = datetime.now(BJ_TZ)
    last_dt = _safe_last_update_time()
    last_raw = _format_dt_for_tql_utc(last_dt)
    updated_threshold = _format_dt_for_tql_utc(last_dt)

    max_results = int(payload.get("maxResults", 500) or 500)
    max_pages = int(payload.get("maxPages", 200) or 200)

    # 增量拉列表：updated >= last_update_time，仅 Issues
    inc_payload = dict(payload)
    inc_payload.update(
        {
            "userId": user_id,
            "projectId": project_id,
            "scenarioFieldConfigIds": [ISSUE_SCENARIO_FIELD_CONFIG_ID],
            "query": "(updated >= '{t0}')".format(t0=updated_threshold),
            "maxResults": max_results,
            "maxPages": max_pages,
            "force_refresh": True,
        }
    )
    inc_res = query_project_tasks_service(inc_payload)
    if not inc_res.get("success"):
        return {"success": False, "error": inc_res.get("error", "issue incremental query failed"), "data": inc_res}

    # 写 ProgramIssue A 表
    a_out = sync_project_tasks_to_db(inc_payload, query_result=inc_res)
    if not a_out.get("success"):
        return {"success": False, "error": a_out.get("error", "sync issue A failed"), "data": a_out.get("data") or {}}

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

    ding = (inc_res.get("data") or {}).get("dingtalk") or {}
    all_rows = ding.get("result") if isinstance(ding.get("result"), list) else []
    inc_specs: List[Dict[str, str]] = []
    for r in all_rows:
        if not isinstance(r, dict):
            continue
        tid = str(r.get("taskId") or "").strip()
        ex = str(r.get("executorId") or "").strip()
        if not tid or not ex:
            continue
        inc_specs.append({"task_id": tid, "executor_id": ex, "project_id": project_id})

    inc_ok = 0
    inc_fail = 0
    inc_failures: List[Dict[str, Any]] = []
    if inc_specs:
        sess = SessionLocal()
        pending_commit = 0
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
                _sync_one_issue_detail(
                    sess,
                    executor_id=spec["executor_id"],
                    task_id=spec["task_id"],
                    project_id=spec["project_id"],
                    item=item,
                    field_id=field_id,
                    now=now,
                    business_type_mapping=business_type_mapping,
                )
                pending_commit += 1
                if pending_commit >= DEFAULT_DB_COMMIT_BATCH_SIZE:
                    sess.commit()
                    pending_commit = 0
                inc_ok += 1
            if pending_commit > 0:
                sess.commit()
        finally:
            sess.close()
    _record_sync_failures(
        sync_type="normal_issue_update",
        project_id=project_id,
        phase="issue_incremental_bc",
        failures=inc_failures,
        retry_round=None,
    )

    if not skip_update_time:
        _upsert_config_value("last_update_time", now_bj.isoformat())
    print(
        "[normal_issue_update] success projectId={} userId={} inc_count={}".format(
            project_id,
            user_id,
            len(inc_specs),
        )
    )

    return {
        "success": True,
        "data": {
            "beijing_now": now_bj.isoformat(),
            "last_update_time_before": str(last_raw or ""),
            "incremental_query": {
                "updated_gte": updated_threshold,
                "maxResults": max_results,
                "maxPages": max_pages,
            },
            "a_sync": a_out.get("data") or {},
            "issue_incremental_detail": {"count": len(inc_specs), "ok": inc_ok, "fail": inc_fail, "failures": inc_failures[:20]},
        },
    }


def benti_team_incremental_update_service(payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """本体团队去重增量更新：20 名本体成员各查一次，任务明细全局只查一次。

    与清表全量更新保持同一数据口径，但这里只做 upsert：
    - 仅导航组、对接组（team_id 0/1），不查询或写入算法组；
    - 单次列表查询同时接收 DEV、Issue，跨成员按 taskId 去重；
    - 所有远端列表和明细成功后才写库并推进 last_update_time；
    - 明细请求并发执行，失败最多重试三轮。
    """
    payload = dict(payload or {})
    project_id = str(payload.get("projectId") or payload.get("projectid") or "").strip()
    if not project_id:
        return {"success": False, "error": "missing projectId", "data": {}}

    owner = "benti_incremental@{}".format(int(time.time()))
    lock = _acquire_update_lock(DEFAULT_UPDATE_LOCK_KEY, owner, ttl_sec=60 * 60 * 2)
    if not lock.get("ok"):
        return {
            "success": False,
            "error": lock.get("error", "update is in progress"),
            "data": {"lock": lock.get("lock") or {}},
        }

    try:
        member_ids = sorted(_load_allowed_executor_ids())
        if not member_ids:
            return {"success": False, "error": "no benti members found", "data": {}}

        last_dt = _safe_last_update_time()
        updated_threshold = _format_dt_for_tql_utc(last_dt)
        token_result = get_valid_access_token(payload)
        if not token_result.get("ok"):
            return {
                "success": False,
                "error": token_result.get("error", "failed to fetch dingtalk token"),
                "data": {},
            }
        access_token = str(token_result.get("access_token") or "")

        max_results = int(payload.get("maxResults", 500) or 500)
        max_pages = int(payload.get("maxPages", 200) or 200)
        allowed_scenarios = {
            DEFAULT_SCENARIO_FIELD_CONFIG_ID,
            ISSUE_SCENARIO_FIELD_CONFIG_ID,
        }
        tasks_by_id: Dict[str, Dict[str, Any]] = {}
        list_results: Dict[str, Dict[str, Any]] = {}

        for member_id in member_ids:
            query_payload = {
                "userId": member_id,
                "projectId": project_id,
                "access_token": access_token,
                "query": "(updated >= '{}')".format(updated_threshold),
                "maxResults": max_results,
                "maxPages": max_pages,
                "force_refresh": True,
                "retries": 2,
            }
            result: Dict[str, Any] = {}
            attempts = 0
            for attempts in range(1, 4):
                result = query_project_tasks_service(query_payload)
                if result.get("success"):
                    break
            if not result.get("success"):
                return {
                    "success": False,
                    "error": "member list failed user={}: {}".format(
                        member_id, result.get("error", "unknown")
                    ),
                    "data": {
                        "memberCount": len(member_ids),
                        "completedMembers": len(list_results),
                        "listResults": list_results,
                    },
                }

            ding = (result.get("data") or {}).get("dingtalk") or {}
            rows = ding.get("result") if isinstance(ding.get("result"), list) else []
            accepted = 0
            for item in rows:
                if not isinstance(item, dict):
                    continue
                scenario_id = str(
                    item.get("scenarioFieldConfigId")
                    or item.get("scenariofieldconfigId")
                    or ""
                )
                task_id = str(item.get("taskId") or "").strip()
                if scenario_id not in allowed_scenarios or not task_id:
                    continue
                tasks_by_id.setdefault(task_id, item)
                accepted += 1
            list_results[member_id] = {
                "attempts": attempts,
                "pages": int((result.get("meta") or {}).get("page_count") or 0),
                "fetched": len(rows),
                "accepted": accepted,
                "uniqueTotal": len(tasks_by_id),
            }

        allowed_executors = set(member_ids)
        filtered_tasks: Dict[str, Dict[str, Any]] = {}
        skipped_executors = {"dev": 0, "issue": 0}
        detail_specs: List[tuple[str, str, str]] = []
        for task_id, item in tasks_by_id.items():
            scenario_id = str(
                item.get("scenarioFieldConfigId")
                or item.get("scenariofieldconfigId")
                or ""
            )
            kind = "dev" if scenario_id == DEFAULT_SCENARIO_FIELD_CONFIG_ID else "issue"
            executor_id = str(item.get("executorId") or "").strip()
            if not executor_id or executor_id not in allowed_executors:
                skipped_executors[kind] += 1
                continue
            filtered_tasks[task_id] = item
            detail_specs.append((kind, executor_id, task_id))

        detail_specs = list(dict.fromkeys(detail_specs))

        def _fetch_detail(spec: tuple[str, str, str]) -> Dict[str, Any]:
            kind, executor_id, task_id = spec
            result = query_user_tasks_service({
                "userId": executor_id,
                "taskId": task_id,
                "projectId": project_id,
                "access_token": access_token,
                "force_refresh": True,
            })
            item = _extract_detail_item(result) if result.get("success") else None
            return {
                "success": bool(result.get("success") and isinstance(item, dict)),
                "kind": kind,
                "executorId": executor_id,
                "taskId": task_id,
                "item": item,
                "error": result.get("error") if not result.get("success") else (
                    "empty detail" if not item else ""
                ),
            }

        pending = list(detail_specs)
        fetched_details: Dict[tuple[str, str, str], Dict[str, Any]] = {}
        last_failures: Dict[tuple[str, str, str], Dict[str, Any]] = {}
        for _round in range(1, 4):
            if not pending:
                break
            next_pending: List[tuple[str, str, str]] = []
            with ThreadPoolExecutor(max_workers=max(1, min(5, len(pending)))) as pool:
                futures = {pool.submit(_fetch_detail, spec): spec for spec in pending}
                for future in as_completed(futures):
                    spec = futures[future]
                    try:
                        result = future.result()
                    except Exception as exc:
                        result = {
                            "success": False,
                            "kind": spec[0],
                            "executorId": spec[1],
                            "taskId": spec[2],
                            "item": None,
                            "error": repr(exc),
                        }
                    if result.get("success"):
                        fetched_details[spec] = result
                        last_failures.pop(spec, None)
                    else:
                        next_pending.append(spec)
                        last_failures[spec] = result
            pending = next_pending

        if pending:
            failures = [last_failures[spec] for spec in pending[:20]]
            _record_sync_failures(
                sync_type="benti_team_incremental",
                project_id=project_id,
                phase="detail_fetch",
                failures=failures,
                retry_round=3,
            )
            return {
                "success": False,
                "error": "{} task details failed after 3 rounds".format(len(pending)),
                "data": {
                    "memberCount": len(member_ids),
                    "uniqueTaskCount": len(tasks_by_id),
                    "detailCount": len(detail_specs),
                    "failedDetails": len(pending),
                    "failures": failures,
                    "skippedExecutors": skipped_executors,
                },
            }

        merged_query_result = {
            "success": True,
            "data": {"dingtalk": {"result": list(filtered_tasks.values())}},
            "meta": {"source": "benti_incremental_deduplicated"},
        }
        a_result = sync_project_tasks_to_db(
            {
                "projectId": project_id,
                "scenarioFieldConfigIds": [
                    DEFAULT_SCENARIO_FIELD_CONFIG_ID,
                    ISSUE_SCENARIO_FIELD_CONFIG_ID,
                ],
            },
            query_result=merged_query_result,
        )
        if not a_result.get("success"):
            return {
                "success": False,
                "error": a_result.get("error", "sync A failed"),
                "data": a_result.get("data") or {},
            }

        field_id = str(
            payload.get("workHourFieldId")
            or os.getenv("TB_TOOL_BT_WORKHOUR_FIELD_ID")
            or os.getenv("TB_TOOL_B1_WORKHOUR_FIELD_ID")
            or DEFAULT_WORKHOUR_FIELD_ID
        )
        business_mapping = _get_business_type_tag_mapping()
        status_mapping = _get_task_flow_status_mapping()
        session = SessionLocal()
        written = {"dev": 0, "issue": 0}
        pending_commit = 0
        try:
            for spec in detail_specs:
                result = fetched_details[spec]
                if result["kind"] == "dev":
                    _sync_one_detail_to_b_and_c(
                        session,
                        executor_id=result["executorId"],
                        task_id=result["taskId"],
                        project_id=project_id,
                        item=result["item"],
                        field_id=field_id,
                        now=datetime.now(timezone.utc),
                        business_type_mapping=business_mapping,
                        task_flow_status_mapping=status_mapping,
                        write_b=True,
                        write_c=True,
                    )
                else:
                    _sync_one_issue_detail(
                        session,
                        executor_id=result["executorId"],
                        task_id=result["taskId"],
                        project_id=project_id,
                        item=result["item"],
                        field_id=field_id,
                        now=datetime.now(timezone.utc),
                        business_type_mapping=business_mapping,
                    )
                written[result["kind"]] += 1
                pending_commit += 1
                if pending_commit >= DEFAULT_DB_COMMIT_BATCH_SIZE:
                    session.commit()
                    pending_commit = 0
            if pending_commit:
                session.commit()
        except Exception as exc:
            session.rollback()
            return {"success": False, "error": "detail write failed: {}".format(exc), "data": {}}
        finally:
            session.close()

        from base.api_monitor import BJ_TZ
        completed_at = datetime.now(BJ_TZ).isoformat()
        _upsert_config_value("last_update_time", completed_at)
        return {
            "success": True,
            "data": {
                "memberCount": len(member_ids),
                "updatedGte": updated_threshold,
                "listResults": list_results,
                "uniqueTaskCountBeforeExecutorFilter": len(tasks_by_id),
                "uniqueTaskCount": len(filtered_tasks),
                "detailCount": len(detail_specs),
                "written": written,
                "skippedExecutors": skipped_executors,
                "lastUpdateTime": completed_at,
                "aSync": a_result.get("data") or {},
            },
        }
    finally:
        _release_update_lock(DEFAULT_UPDATE_LOCK_KEY, owner)


# ---------------------------------------------------------------------------
# 便捷入口：四个主体函数
#   tb_full_update_service        — ⚠️ 已关闭 (2026-07-16)，改为手动执行。见文件底部注释
#   increase_sync (in base/projects/routes.py) — 当前团队同步唯一入口
# ---------------------------------------------------------------------------


# ═══════════════════════════════════════════════════════════════════════
# tb_full_update_service — TB大更新（清表全量）
#
# ⚠️ 已关闭（2026-07-16）。
#    此函数会清空全部 A/B/C/program_issue 表并全量重拉所有用户，
#    月 API 配额消耗极大（每人 2 次 × 用户数），改为手动执行。
#
# 手动执行方式（进入 backend 目录后 Python shell）：
#
#     from base.sync.task_sync import tb_full_update_service
#     from base.dingtalk_client import get_config_projectids
#     pids = get_config_projectids()
#     pid = next(iter(pids.values()))
#     result = tb_full_update_service({"projectId": pid})
#     print(result)
#
# ═══════════════════════════════════════════════════════════════════════
#
# def tb_full_update_service(payload: Dict[str, Any]) -> Dict[str, Any]:
#     """TB全量更新：清空工时五表，全量重拉所有用户。
#
#     1) TRUNCATE 五表 (project_tasks / project_task_details / project_task_overdue_details / program_issue / program_issue_detail)
#     2) last_update_time 重置为 365 天前（限定重拉范围，避免全量打爆）
#     3) 遍历 user_character 所有用户，DEV + Issue 全量拉取
#     4) 统一推进 last_update_time
#
#     注意：知识库更新由调用方独立执行，此处不动。
#     """
#     payload = dict(payload or {})
#     project_id = str(payload.get("projectId") or payload.get("projectid") or "").strip()
#     if not project_id:
#         return {"success": False, "error": "missing projectId", "data": {}}
#
#     from base.config.service import is_full_sync_enabled
#     if not is_full_sync_enabled():
#         return {"success": False, "error": "sync is disabled (full_sync_enabled = false)", "data": {}}
#
#     owner = "tb_full@{}".format(int(time.time()))
#     lock = _acquire_update_lock(DEFAULT_UPDATE_LOCK_KEY, owner)
#     if not lock.get("ok"):
#         return {"success": False, "error": lock.get("error", "update is in progress"), "data": lock.get("lock") or {}}
#
#     from base.api_monitor import enter_full_sync_mode, leave_full_sync_mode
#     enter_full_sync_mode()
#
#     try:
#         # 1) 清空工时五表（DEV + Issue）
#         print("[tb_full] TRUNCATE 工时五表...")
#         sess = SessionLocal()
#         try:
#             sess.execute(text("DELETE FROM project_task_overdue_details"))
#             sess.execute(text("DELETE FROM project_task_details"))
#             sess.execute(text("DELETE FROM project_tasks"))
#             sess.execute(text("DELETE FROM program_issue_detail"))
#             sess.execute(text("DELETE FROM program_issue"))
#             sess.commit()
#             print("[tb_full] 工时五表已清空")
#         except Exception as e:
#             sess.rollback()
#             print("[tb_full] 清表失败:", repr(e))
#             return {"success": False, "error": "truncate tables failed: {}".format(e), "data": {}}
#         finally:
#             sess.close()
#
#         # 2) 重置 last_update_time 为 365 天前（限定重拉范围，避免全量打爆）
#         one_year_ago = (datetime.now(timezone.utc) - timedelta(days=365)).isoformat()
#         _upsert_config_value("last_update_time", one_year_ago)
#         print(f"[tb_full] last_update_time → 365 days ago: {one_year_ago}")
#
#         # 3) 获取所有用户
#         sess2 = SessionLocal()
#         try:
#             rows = sess2.query(DbUserCharacter.user_id).all()
#             user_ids = [str(r[0]).strip() for r in rows if r and str(r[0]).strip()]
#         finally:
#             sess2.close()
#
#         if not user_ids:
#             return {"success": False, "error": "no users found in user_character", "data": {}}
#
#         dev_ok = 0
#         dev_fail = 0
#         issue_ok = 0
#         issue_fail = 0
#         total_bc_count = 0
#
#         for uid in user_ids:
#             shared = {"userId": uid, "projectId": project_id}
#
#             # DEV
#             dev_out = normal_incremental_update_service(shared, skip_update_time=True)
#             if dev_out.get("success"):
#                 dev_ok += 1
#                 total_bc_count += dev_out.get("data", {}).get("incremental_bc", {}).get("count", 0)
#             else:
#                 dev_fail += 1
#
#             # Issue
#             issue_out = normal_issue_incremental_update_service(shared, skip_update_time=True)
#             if issue_out.get("success"):
#                 issue_ok += 1
#             else:
#                 issue_fail += 1
#
#         print(f"[tb_full] DEV: {dev_ok}ok/{dev_fail}fail  Issue: {issue_ok}ok/{issue_fail}fail  users: {len(user_ids)}  bc_total: {total_bc_count}")
#
#         # 4) 统一推进 last_update_time
#         from base.api_monitor import BJ_TZ
#         now_bj = datetime.now(BJ_TZ).isoformat()
#         _upsert_config_value("last_update_time", now_bj)
#         print(f"[tb_full] last_update_time → {now_bj}")
#
#         return {
#             "success": True,
#             "data": {
#                 "beijing_now": now_bj,
#                 "user_count": len(user_ids),
#                 "dev": {"ok": dev_ok, "fail": dev_fail},
#                 "issue": {"ok": issue_ok, "fail": issue_fail},
#                 "truncated": True,
#             },
#         }
#     finally:
#         leave_full_sync_mode()
#         _release_update_lock(DEFAULT_UPDATE_LOCK_KEY, owner)
