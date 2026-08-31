"""Dashboard personal-hours routes and payload builder.

Routes:
  GET  /personal-hours         - Default personal hours dashboard data
  GET  /personal-hours/members - Member selector options
  POST /personal-hours/query   - Query with custom time range
  POST /personal-hours/update  - Trigger task data sync for a time range
"""

from datetime import datetime
import time

from flask import request

from base.auth.access import require_access
from base.config.service import (
    get_default_time_range_service,
    touch_last_update_time_service,
    get_workhour_role_coefficients_service,
)
from base.sync.task_sync import sync_project_details_in_time_range_service
from workhour.personal.aggregate import workdays_in_range_service
from base.dingtalk_client import get_config_projectids
from base.organization.service import list_all_members, resolve_sync_operator_id
from base.organization.constants import ROLE_LABELS

from base.route_registry.dashboard import (
    _fail,
    _ok,
    _require_login,
    dashboard_bp,
)


def _load_user_character_members():
    """Load all members from the user_character DB table.

    Returns stable organization fields for personal-hours selectors.
    """
    members = []
    for row in list_all_members():
        uid = str(row.get("userId") or "").strip()
        if not uid:
            continue
        # 算法组使用独立数据源，不出现在个人工时下拉中。
        if row.get("teamCode") == "ALGORITHM":
            continue
        members.append(
            {
                "id": uid,
                "name": row.get("userName") or uid,
                "userId": uid,
                "teamCode": row.get("teamCode") or "",
                "teamName": row.get("teamName") or "未分组",
                "jobRoleCode": row.get("jobRoleCode") or "",
                "jobRoleName": row.get("jobRoleName") or "",
            }
        )
    return members


def _filter_member_options_by_scope(member_options, user):
    """Apply the authenticated user's explicit data scope to selector rows."""
    options = [
        member for member in list(member_options or [])
        if member.get("jobRoleCode") != "SYSTEM_ADMIN"
    ]
    if str((user or {}).get("dataScope") or "") == "team":
        team_code = str((user or {}).get("teamCode") or "").strip().upper()
        return [member for member in options if member.get("teamCode") == team_code]
    return options


def _load_single_user_character_member(user_id: str, user_name: str = ""):
    """Load a single member through the stable roster service."""
    uid = str(user_id or "").strip()
    uname = str(user_name or "").strip()
    if not uid and not uname:
        return None

    row = next((member for member in list_all_members() if (
        (uid and member.get("userId") == uid)
        or (uname and member.get("userName") == uname)
    )), None)
    if not row:
        return None
    return {
        "id": row.get("userId") or "",
        "name": row.get("userName") or uid or uname,
        "userId": row.get("userId") or "",
        "teamCode": row.get("teamCode") or "",
        "teamName": row.get("teamName") or "未分组",
        "jobRoleCode": row.get("jobRoleCode") or "",
        "jobRoleName": row.get("jobRoleName") or "未设置",
    }


def _build_default_personal_hours_payload(user, target: str):
    """Build the full personal-hours dashboard payload for a given user and target.

    This is the core data builder used by all personal-hours endpoints.
    It loads time ranges, member lists, workday calculations, and coefficients.
    """
    tr = get_default_time_range_service() or {}
    if not tr.get("success"):
        tr = {}

    def _to_datetime_local_value(raw: str) -> str:
        """Convert ISO datetime to datetime-local format (no timezone suffix)."""
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

    start_time = _to_datetime_local_value(tr.get("start_time") or "")
    end_time = _to_datetime_local_value(tr.get("end_time") or "")
    last_update_time = str(tr.get("last_update_time") or "")

    dashboard = {
        "defaultRange": {"startDate": start_time, "endDate": end_time},
        "lastUpdatedAt": last_update_time,
        "compensatoryDays": 0,
        "statutoryHolidays": [],
        "scheduledEffectiveHours": 0,
        "completedEffectiveHours": 0,
        "quarterlyOverdueEffectiveHours": 0,
        "quarterlyOverdueCompletedHours": 0,
        "quarterlyPlannedEffectiveHours": 0,
        "quarterlyPlannedCompletedHours": 0,
        "taskDistribution": [],
        "taskDetails": [],
        "targetLabel": target,
        "workdayCount": 0.0,
        "expectedEffectiveDays": 0.0,
        "expectedCoefficient": 1.0,
        "calendarSource": "",
        "timezone": "",
    }

    role = str((user or {}).get("role") or "").strip().lower()
    user_id = str((user or {}).get("user_id") or "").strip()
    user_name = str((user or {}).get("name") or "").strip()
    coeff_out = get_workhour_role_coefficients_service() or {}
    workhour_role_coefficients = coeff_out.get("workhour_role_coefficients") or {}

    member_options = []
    if role in {"manager", "admin"}:
        all_members = _load_user_character_members()
        scoped_members = _filter_member_options_by_scope(all_members, user)
        member_options = [{
            "id": "ALL", "name": "全部人员", "userId": "",
            "teamCode": "", "teamName": "全部", "jobRoleCode": "", "jobRoleName": "",
        }] + scoped_members
    elif user_id or user_name:
        me = _load_single_user_character_member(user_id=user_id, user_name=user_name)
        if me:
            member_options = [me]
        elif user_id:
            member_options = [{
                "id": user_id,
                "name": user_name or user_id,
                "userId": user_id,
                "teamCode": str((user or {}).get("teamCode") or ""),
                "teamName": str((user or {}).get("teamName") or ""),
                "jobRoleCode": str((user or {}).get("jobRoleCode") or ""),
                "jobRoleName": str((user or {}).get("jobRoleName") or ""),
            }]
    selected_target = str(target or "").strip() or "ALL"
    member_ids = {str(item.get("id") or "").strip() for item in member_options}
    if selected_target not in member_ids:
        if "ALL" in member_ids:
            selected_target = "ALL"
        else:
            selected_target = next((mid for mid in member_ids if mid), "")
    if selected_target == "ALL":
        target_label = "全部人员"
    else:
        hit = next((x for x in member_options if str(x.get("id") or "") == selected_target), None)
        target_label = str((hit or {}).get("name") or selected_target)
    dashboard["targetLabel"] = target_label

    target_role_code = ""
    target_hit = next((x for x in member_options if str(x.get("id") or "") == selected_target), None)
    if target_hit:
        target_role_code = str(target_hit.get("jobRoleCode") or "")

    coeff = 1.0
    if target_role_code:
        coeff = float(workhour_role_coefficients.get(target_role_code, 1.0) or 1.0)
    wd_out = workdays_in_range_service({
        "start_time": start_time,
        "end_time": end_time,
        "compensatoryDays": 0,
    }) or {}
    wd_data = wd_out.get("data") or {}
    raw_workday_count = float(wd_data.get("workday_count") or 0.0)
    month_workdays = wd_data.get("month_workdays") or []
    dashboard["workdayCount"] = round(raw_workday_count, 2)
    dashboard["expectedCoefficient"] = coeff
    dashboard["expectedEffectiveDays"] = round(raw_workday_count * coeff, 2)
    dashboard["calendarSource"] = str(wd_data.get("calendar_source") or "")
    dashboard["timezone"] = str(wd_data.get("timezone") or "")

    return {
        "trend": [
            {"month": str(item.get("month") or ""), "total": float(item.get("day") or 0)}
            for item in month_workdays
            if str(item.get("month") or "").strip()
        ],
        "dashboard": dashboard,
        "workhourRoleCoefficients": workhour_role_coefficients,
        "memberOptions": member_options,
        "selectedTarget": selected_target,
    }


def _public_member_option(member):
    role_code = str(member.get("jobRoleCode") or "").strip()
    team_code = str(member.get("teamCode") or "").strip()
    return {
        "id": str(member.get("id") or member.get("userId") or "").strip(),
        "name": str(member.get("name") or member.get("userName") or "").strip(),
        "userId": str(member.get("userId") or member.get("id") or "").strip(),
        "teamCode": team_code,
        "teamName": str(member.get("teamName") or "").strip(),
        "jobRoleCode": role_code,
        "jobRoleName": str(member.get("jobRoleName") or ROLE_LABELS.get(role_code, "")).strip(),
    }


def _public_personal_hours_payload(payload):
    """Remove legacy organization fields from personal-hours HTTP payloads."""
    result = dict(payload or {})
    result["memberOptions"] = [
        _public_member_option(member)
        for member in result.get("memberOptions", [])
    ]
    result["workhourRoleCoefficients"] = dict(result.get("workhourRoleCoefficients") or {})
    return result


@dashboard_bp.route("/personal-hours", methods=["GET"])
def personal_hours():
    """Get default personal-hours dashboard (current user, default time range)."""
    user = _require_login()
    if not user:
        return _fail("unauthenticated", code=401, data={})
    target = (request.args.get("target") or user.get("user_id") or user.get("name") or "").strip()
    if not target:
        target = "ALL"
    return _ok(_public_personal_hours_payload(_build_default_personal_hours_payload(user, target)))


@dashboard_bp.route("/personal-hours/members", methods=["GET"])
def personal_hours_members():
    """Get member selector options for the personal-hours page."""
    user = _require_login()
    if not user:
        return _fail("unauthenticated", code=401, data={})
    target = (user.get("user_id") or user.get("name") or "").strip() or "ALL"
    out = _build_default_personal_hours_payload(user, target)
    return _ok({
        "memberOptions": _public_personal_hours_payload(out).get("memberOptions") or [],
        "selectedTarget": out.get("selectedTarget") or target,
    })


@dashboard_bp.route("/personal-hours/query", methods=["POST"])
def personal_hours_query():
    """Query personal-hours data with a custom time range from the frontend."""
    user = _require_login()
    if not user:
        return _fail("unauthenticated", code=401, data={})
    payload = request.get_json(silent=True) or {}
    target = str(payload.get("target") or user.get("user_id") or user.get("name") or "").strip() or "ALL"
    out = _build_default_personal_hours_payload(user, target)
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
    # Recalculate workdays with frontend-provided date range
    start_date = str((out.get("dashboard") or {}).get("defaultRange", {}).get("startDate") or "")
    end_date = str((out.get("dashboard") or {}).get("defaultRange", {}).get("endDate") or "")
    coeff_map = out.get("workhourRoleCoefficients") or {}
    member_options = out.get("memberOptions") or []
    target_role_code = ""
    target_hit = next((x for x in member_options if str(x.get("id") or "") == target), None)
    if target_hit:
        target_role_code = str(target_hit.get("jobRoleCode") or "")
    coeff = 1.0
    if target_role_code:
        coeff = float(coeff_map.get(target_role_code, 1.0) or 1.0)
    wd_out = workdays_in_range_service({
        "start_time": start_date, "end_time": end_date, "compensatoryDays": 0,
    }) or {}
    wd_data = wd_out.get("data") or {}
    raw_workday_count = float(wd_data.get("workday_count") or 0.0)
    month_workdays = wd_data.get("month_workdays") or []
    out["dashboard"]["workdayCount"] = round(raw_workday_count, 2)
    out["dashboard"]["expectedCoefficient"] = coeff
    out["dashboard"]["expectedEffectiveDays"] = round(raw_workday_count * coeff, 2)
    out["dashboard"]["calendarSource"] = str(wd_data.get("calendar_source") or "")
    out["dashboard"]["timezone"] = str(wd_data.get("timezone") or "")
    out["trend"] = [
        {"month": str(item.get("month") or ""), "total": float(item.get("day") or 0)}
        for item in month_workdays
        if str(item.get("month") or "").strip()
    ]
    return _ok(_public_personal_hours_payload(out))


@dashboard_bp.route("/personal-hours/update", methods=["POST"])
def personal_hours_update():
    """Trigger task data sync for a time range, then update last_update_time."""
    user, denied = require_access(_fail, any_roles=("manager", "admin"))
    if denied:
        return denied

    payload = request.get_json(silent=True) or {}
    is_full_sync = bool(payload.get("fullSync"))

    def _resolve_operator_user_id() -> str:
        """Auto-select an operator from the database roster."""
        return resolve_sync_operator_id()

    user_id = _resolve_operator_user_id()
    if not user_id:
        return _fail("missing operator userId in database roster", code=400, data={})

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
        "startDate": payload.get("startDate"),
        "endDate": payload.get("endDate"),
        "target": payload.get("target"),
        "force_refresh": True,
    }
    sync_out = sync_project_details_in_time_range_service(sync_payload)

    if not sync_out.get("success"):
        return _fail(sync_out.get("error", "sync failed"), code=500, data=sync_out.get("data") or {})

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

    return _ok({
        "message": f"已触发{target_label}的{'全量更新' if is_full_sync else '工时更新'}。",
        "lastUpdatedAt": last_updated,
        "fullSync": is_full_sync,
        "elapsedMs": elapsed_ms,
        "projectId": project_id,
        "sync": sync_out.get("data") or {},
    })
