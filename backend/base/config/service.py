import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from base.dingtalk_client import get_config_projectids
from base.organization.constants import ROLE_LABELS, stable_role_code
from base.organization.service import list_all_members

DEFAULT_WORKHOUR_COEFFICIENT = 1.0


def _parse_role_coefficients(raw: Any) -> Dict[str, float]:
    """Parse a stable job_role_code -> coefficient JSON mapping."""
    if raw is None:
        return {}
    try:
        data = raw
        if isinstance(raw, str):
            data = json.loads(raw)
        if not isinstance(data, dict):
            return {}

        out: Dict[str, float] = {}
        for raw_k, raw_v in data.items():
            role_code = stable_role_code(raw_k)
            if not role_code:
                continue
            try:
                v_float = float(raw_v)
            except Exception:
                continue
            if v_float < 0:
                continue
            out[role_code] = v_float

        return out
    except Exception:
        return {}


def get_userids_service() -> Dict[str, Any]:
    users: List[Dict[str, str]] = [
        {
            "name": str(member.get("userName") or member.get("userId") or ""),
            "userId": str(member.get("userId") or ""),
        }
        for member in list_all_members()
        if str(member.get("userId") or "").strip()
    ]
    return {"success": True, "users": users}


def get_projectids_service() -> Dict[str, Any]:
    projectids = get_config_projectids()
    projects: List[Dict[str, str]] = []
    for name, project_id in projectids.items():
        projects.append({"name": str(name), "projectId": str(project_id)})
    return {"success": True, "projects": projects}

def get_workhour_role_coefficients_service() -> Dict[str, Any]:
    """Read the authoritative job_role_code -> coefficient mapping."""
    from base.db.engine import SessionLocal
    from base.db.orm import Config as DbConfig

    session = SessionLocal()
    try:
        row = session.query(DbConfig).filter(DbConfig.type_ == "workhour_role_coefficients").first()
        mapping = _parse_role_coefficients(getattr(row, "value", None) if row else None)
        return {
            "success": True,
            "workhour_role_coefficients": mapping,
        }
    finally:
        session.close()


def get_user_character_service(user_id: str) -> Dict[str, Any]:
    """Resolve a user's stable job role and its work-hour coefficient."""
    from base.db.engine import SessionLocal
    from base.db.orm import Config as DbConfig
    from base.db.orm import UserCharacter as DbUserCharacter

    user_id = str(user_id or "").strip()
    session = SessionLocal()
    try:
        # 1) 读取映射
        row = session.query(DbConfig).filter(DbConfig.type_ == "workhour_role_coefficients").first()
        mapping = _parse_role_coefficients(getattr(row, "value", None) if row else None)

        # 2) 读取 user_character
        c_row = (
            session.query(DbUserCharacter)
            .filter(DbUserCharacter.user_id == user_id)
            .first()
        )
        job_role_code = stable_role_code(getattr(c_row, "job_role_code", None))
        coefficient = float(mapping.get(job_role_code, DEFAULT_WORKHOUR_COEFFICIENT))
        return {
            "success": True,
            "userId": user_id,
            "jobRoleCode": job_role_code,
            "jobRoleName": ROLE_LABELS.get(job_role_code, "未设置"),
            "workhour_coefficient": coefficient,
        }
    finally:
        session.close()


def get_last_update_time_service() -> Dict[str, Any]:
    """
    读取 config 表里的 last_update_time（不再提供 time_range）。
    返回值的字符串格式与数据库 value 保持一致（前端负责展示/解析）。
    """
    from base.db.engine import SessionLocal
    from base.db.orm import Config as DbConfig

    session = SessionLocal()
    try:
        row = session.query(DbConfig).filter(DbConfig.type_ == "last_update_time").first()
        return {
            "success": True,
            "last_update_time": str(getattr(row, "value", "") or "") if row else "",
        }
    finally:
        session.close()


def get_default_time_range_service() -> Dict[str, Any]:
    """
    只读：读取 config 表里的 start_time / end_time / last_update_time，用于页面初始化默认值。
    注意：本服务不提供写入接口；更新/同步时由前端传入 startDate/endDate 控制时间窗。
    """
    from base.db.engine import SessionLocal
    from base.db.orm import Config as DbConfig

    session = SessionLocal()
    try:
        def _get(t: str) -> str:
            row = session.query(DbConfig).filter(DbConfig.type_ == t).first()
            return str(getattr(row, "value", "") or "") if row else ""

        return {
            "success": True,
            "start_time": _get("start_time"),
            "end_time": _get("end_time"),
            "last_update_time": _get("last_update_time"),
        }
    finally:
        session.close()


def _upsert_config_value(session, cfg_type: str, value: str) -> None:
    from base.db.orm import Config as DbConfig

    row = session.query(DbConfig).filter(DbConfig.type_ == cfg_type).first()
    if row:
        row.value = value
        return
    session.add(DbConfig(type_=cfg_type, value=value, brief=None))


def touch_last_update_time_service() -> Dict[str, Any]:
    """
    仅更新 config 表里的 last_update_time 为当前时间。
    """
    from base.db.engine import SessionLocal

    now = datetime.now(timezone.utc).isoformat()
    session = SessionLocal()
    try:
        _upsert_config_value(session, "last_update_time", now)
        session.commit()
        return get_last_update_time_service()
    except Exception as e:
        session.rollback()
        return {"success": False, "error": str(e), "data": {}}
    finally:
        session.close()


def update_endtime_service() -> Dict[str, Any]:
    """
    将 config.end_time 更新为“今天所在季度的季度末(UTC) 23:59:59”。
    """
    from base.db.engine import SessionLocal
    from base.db.orm import Config as DbConfig

    session = SessionLocal()
    try:
        row = session.query(DbConfig).filter(DbConfig.type_ == "end_time").first()
        now_utc = datetime.now(timezone.utc)

        old_raw = str(getattr(row, "value", "") or "").strip() if row else ""
        quarter_end_month = ((now_utc.month - 1) // 3 + 1) * 3
        if quarter_end_month == 12:
            next_month_first = datetime(now_utc.year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            next_month_first = datetime(now_utc.year, quarter_end_month + 1, 1, tzinfo=timezone.utc)
        quarter_end_day = (next_month_first - timedelta(days=1)).day
        new_dt = datetime(
            now_utc.year,
            quarter_end_month,
            quarter_end_day,
            23,
            59,
            59,
            tzinfo=timezone.utc,
        )

        new_value = new_dt.isoformat()
        if row:
            row.value = new_value
        else:
            session.add(DbConfig(type_="end_time", value=new_value, brief=None))

        session.commit()
        return {
            "success": True,
            "end_time": new_value,
            "old_end_time": old_raw,
        }
    except Exception as e:
        session.rollback()
        return {"success": False, "error": str(e), "data": {}}
    finally:
        session.close()


def get_workhour_auto_calc_service() -> Dict[str, Any]:
    """
    读取自动更新配置（对应 config 三字段）：
    - type: is_auto_update, value: 1/0
    - type: auto_update_time, value: HH:MM
    - type: last_update_time, value: ISO（用于后端去重触发；前端无需展示在此接口里）
    """
    from base.db.engine import SessionLocal
    from base.db.orm import Config as DbConfig

    session = SessionLocal()
    try:
        def _get(t: str) -> str:
            row = session.query(DbConfig).filter(DbConfig.type_ == t).first()
            return str(getattr(row, "value", "") or "") if row else ""

        enabled_raw = _get("is_auto_update")
        enabled = str(enabled_raw).strip().lower() in {"1", "true", "yes", "on"}
        auto_time = _get("auto_update_time") or "09:00"
        return {
            "success": True,
            "auto_calc_enabled": enabled,
            "auto_calc_time": auto_time,
            # last_date 由 last_update_time 在后端控制去重，本接口返回空值即可
            "auto_calc_last_date": "",
        }
    finally:
        session.close()


def is_sync_enabled() -> bool:
    """
    日常同步开关，由 api_monitor 自动管理。

    读取 config 表 type='daily_sync_enabled'（兼容旧 key 'knowledge_sync_enabled'）：
      'true' / 无记录  → True  (允许)
      'false'/'0'     → False (当日 API 限额已满，禁止)
    """
    from base.db.engine import SessionLocal
    from base.db.orm import Config as DbConfig

    session = SessionLocal()
    try:
        # 优先读新 key，回退旧 key
        row = session.query(DbConfig).filter(DbConfig.type_ == "daily_sync_enabled").first()
        if not row:
            row = session.query(DbConfig).filter(DbConfig.type_ == "knowledge_sync_enabled").first()
        if not row:
            return True
        return str(row.value).strip().lower() not in ("0", "false", "no", "off")
    except Exception:
        return True
    finally:
        session.close()




def update_workhour_auto_calc_service(
    enabled: Any,
    auto_time: str,
) -> Dict[str, Any]:
    """
    更新自动更新配置（对应 config 三字段中的前两项）。
    """
    from base.db.engine import SessionLocal

    enabled_bool = str(enabled).strip().lower() in {"1", "true", "yes", "on"}
    time_str = str(auto_time or "").strip()
    if not time_str:
        time_str = "09:00"

    session = SessionLocal()
    try:
        _upsert_config_value(
            session,
            "is_auto_update",
            "1" if enabled_bool else "0",
        )
        _upsert_config_value(session, "auto_update_time", time_str)
        session.commit()
        return get_workhour_auto_calc_service()
    except Exception as e:
        session.rollback()
        return {"success": False, "error": str(e), "data": {}}
    finally:
        session.close()


def set_workhour_auto_calc_last_date_service(last_date: str) -> Dict[str, Any]:
    # 已按需求改为仅使用 last_update_time 去重；该方法不再写入多余配置字段。
    _ = last_date
    return get_workhour_auto_calc_service()
