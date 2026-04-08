import time
from datetime import datetime

from flask import Blueprint, request, session

from services.config_service import get_default_time_range_service, touch_last_update_time_service
from services.task_sync_service import sync_project_details_in_time_range_service
from dingtalk_client import get_config_projectids, get_config_user_meta, get_config_userids


dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/api/dashboard")


def _ok(data):
    return {"code": 200, "error": "", "data": data}, 200


def _fail(msg, code=400, data=None):
    return {"code": code, "error": msg, "data": data if data is not None else {}}, code


def _require_login():
    user = session.get("auth_user")
    if not user:
        return None
    return user


def _build_default_personal_hours_payload(user, target: str):
    tr = get_default_time_range_service() or {}
    if not tr.get("success"):
        tr = {}

    def _to_datetime_local_value(raw: str) -> str:
        """
        前端 input[type=datetime-local] 需要形如：YYYY-MM-DDTHH:mm:ss（不能带 Z 或 +00:00）。
        后端 config 里可能是 ISO（含时区），这里统一转换为不带时区的字符串。
        """
        s = str(raw or "").strip()
        if not s:
            return ""
        try:
            # 兼容 Z
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            dt = datetime.fromisoformat(s)
            # 去掉时区信息，输出到秒
            return dt.replace(tzinfo=None).strftime("%Y-%m-%dT%H:%M:%S")
        except Exception:
            # 若本来就是 datetime-local 格式，或解析失败，直接返回原值
            return str(raw or "")

    start_time = _to_datetime_local_value(tr.get("start_time") or "")
    end_time = _to_datetime_local_value(tr.get("end_time") or "")
    last_update_time = _to_datetime_local_value(tr.get("last_update_time") or "")

    # PersonalHours.jsx 期望：
    # response.data.dashboard.defaultRange.startDate/endDate + lastUpdatedAt + compensatoryDays
    dashboard = {
        "defaultRange": {
            "startDate": start_time,
            "endDate": end_time,
        },
        "lastUpdatedAt": last_update_time,
        "compensatoryDays": 0,
        "statutoryHolidays": [],
        # 以下字段先给 0/空，后续接真实工时统计再补齐
        "scheduledEffectiveHours": 0,
        "completedEffectiveHours": 0,
        "quarterlyOverdueEffectiveHours": 0,
        "quarterlyOverdueCompletedHours": 0,
        "quarterlyPlannedEffectiveHours": 0,
        "quarterlyPlannedCompletedHours": 0,
        "taskDistribution": [],
        "taskDetails": [],
        "targetLabel": target,
    }

    # memberOptions 先提供最小集合：自己
    member_options = []
    if user and user.get("name"):
        member_options.append({"id": user.get("name"), "name": user.get("name"), "team": user.get("team", "")})

    return {
        "trend": [],
        "dashboard": dashboard,
        "memberOptions": member_options,
        "selectedTarget": target,
    }


@dashboard_bp.route("/personal-hours", methods=["GET"])
def personal_hours():
    user = _require_login()
    if not user:
        return _fail("unauthenticated", code=401, data={})

    target = (request.args.get("target") or user.get("name") or "").strip()
    if not target:
        target = "ALL"
    return _ok(_build_default_personal_hours_payload(user, target))


@dashboard_bp.route("/personal-hours/query", methods=["POST"])
def personal_hours_query():
    user = _require_login()
    if not user:
        return _fail("unauthenticated", code=401, data={})

    payload = request.get_json(silent=True) or {}
    target = str(payload.get("target") or user.get("name") or "").strip() or "ALL"
    out = _build_default_personal_hours_payload(user, target)
    # 回显输入的时间范围（若前端传入）
    if payload.get("startDate") and payload.get("endDate"):
        out["dashboard"]["defaultRange"] = {
            "startDate": str(payload.get("startDate")),
            "endDate": str(payload.get("endDate")),
        }
    if payload.get("compensatoryDays") is not None:
        try:
            out["dashboard"]["compensatoryDays"] = float(payload.get("compensatoryDays") or 0)
        except Exception:
            out["dashboard"]["compensatoryDays"] = 0
    return _ok(out)


@dashboard_bp.route("/personal-hours/update", methods=["POST"])
def personal_hours_update():
    user = _require_login()
    if not user:
        return _fail("unauthenticated", code=401, data={})

    payload = request.get_json(silent=True) or {}
    is_full_sync = bool(payload.get("fullSync"))

    def _resolve_operator_user_id() -> str:
        # 对前端隐藏 userId：由后端从 ids.json 自动选择操作人。
        # 优先 character=0（管理员），否则退化为首个配置 userId。
        meta = get_config_user_meta() or {}
        if isinstance(meta, dict):
            for _name, one in meta.items():
                if not isinstance(one, dict):
                    continue
                try:
                    ch = int(one.get("character", 1) or 1)
                except Exception:
                    ch = 1
                if ch == 0:
                    uid = str(one.get("userId") or "").strip()
                    if uid:
                        return uid

        userids = get_config_userids() or {}
        if isinstance(userids, dict) and userids:
            return str(next(iter(userids.values())) or "").strip()
        return ""

    user_id = _resolve_operator_user_id()
    if not user_id:
        return _fail("missing operator userId in ids/config", code=400, data={})

    # 当前先取配置里的第一个 projectId 作为同步目标；后续可按 team/user 做更细映射。
    projectids = get_config_projectids() or {}
    project_id = ""
    if isinstance(projectids, dict) and projectids:
        project_id = str(next(iter(projectids.values())) or "").strip()
    if not project_id:
        return _fail("missing projectId in ids/config", code=400, data={})

    started_at = time.time()
    sync_payload = {
        "userId": user_id,
        "projectId": project_id,
        # 保留前端传入参数，便于后续扩展
        "startDate": payload.get("startDate"),
        "endDate": payload.get("endDate"),
        "target": payload.get("target"),
        "force_refresh": True,
    }
    # 目前 React 前端已直接调用 /api/bt/full_update 和 /api/bt/time_range_update，
    # 这里保留普通更新路径用于兼容旧调用。
    sync_out = sync_project_details_in_time_range_service(sync_payload)

    if not sync_out.get("success"):
        return _fail(sync_out.get("error", "sync failed"), code=500, data=sync_out.get("data") or {})

    # 同步成功后更新 last_update_time，作为页面“上次更新时间”
    out = touch_last_update_time_service() or {}
    if not out.get("success"):
        return _fail(out.get("error", "failed to update last_update_time"), code=500, data={})

    def _to_datetime_local_value(raw: str) -> str:
        s = str(raw or "").strip()
        if not s:
            return ""
        try:
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            dt = datetime.fromisoformat(s)
            return dt.replace(tzinfo=None).strftime("%Y-%m-%dT%H:%M:%S")
        except Exception:
            return str(raw or "")

    last_updated = _to_datetime_local_value(out.get("last_update_time") or "")
    target = str(payload.get("target") or user.get("name") or "当前对象")
    target_label = "全部人员" if target == "ALL" else target
    elapsed_ms = int((time.time() - started_at) * 1000)

    return _ok(
        {
            "message": f"已触发{target_label}的{'全量更新' if is_full_sync else '工时更新'}。",
            "lastUpdatedAt": last_updated,
            "fullSync": is_full_sync,
            "elapsedMs": elapsed_ms,
            "projectId": project_id,
            "sync": sync_out.get("data") or {},
        }
    )

