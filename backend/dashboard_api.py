import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from flask import Blueprint, request, session
from sqlalchemy import and_, func

from services.config_service import (
    get_default_time_range_service,
    touch_last_update_time_service,
    get_workhour_character_coefficients_service,
)
from services.task_sync_service import sync_project_details_in_time_range_service
from services.workhour_aggregate_service import workdays_in_range_service
from dingtalk_client import get_config_projectids, get_config_user_meta, get_config_userids


dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/api/dashboard")
SH_TZ = ZoneInfo("Asia/Shanghai")


def _ok(data):
    return {"code": 200, "error": "", "data": data}, 200


def _fail(msg, code=400, data=None):
    return {"code": code, "error": msg, "data": data if data is not None else {}}, code


def _require_login():
    user = session.get("auth_user")
    if not user:
        return None
    return user


def _team_name_from_team_id(team_id_value):
    if team_id_value is None:
        return "未分组"
    val = str(team_id_value).strip()
    if val == "0":
        return "导航组"
    if val == "1":
        return "对接组"
    return "未分组"


def _load_user_character_members():
    from db.engine import SessionLocal
    from db.orm import UserCharacter as DbUserCharacter

    session = SessionLocal()
    try:
        rows = session.query(DbUserCharacter).order_by(DbUserCharacter.user_id.asc()).all()
        members = []
        for row in rows:
            uid = str(getattr(row, "user_id", "") or "").strip()
            name = str(getattr(row, "name", "") or "").strip()
            if not uid:
                continue
            members.append(
                {
                    "id": uid,
                    "name": name or uid,
                    "userId": uid,
                    "character": int(getattr(row, "character", 1) or 1),
                    "team": _team_name_from_team_id(getattr(row, "team_id", None)),
                    "teamId": str(getattr(row, "team_id", "") or ""),
                }
            )
        return members
    finally:
        session.close()


def _member_role_label_from_user_character(character_value, is_nav_lead, is_servo_lead):
    """
    岗位定义（按你的最新规则）：
    - 0: 组长
    - 1: 软件开发工程师
    - 2: 软件应用工程师
    - 3: 应用工程师
    - 4: 算法工程师
    """
    try:
        c = int(character_value)
    except Exception:
        c = 1

    if c == 0:
        return "组长"
    if c == 1:
        return "软件开发工程师"
    if c == 2:
        return "软件应用工程师"
    if c == 3:
        return "应用工程师"
    if c == 4:
        return "算法工程师"
    return "软件开发工程师"


def _current_quarter_utc_range(expected_mode: str = "quarter"):
    """
    统计窗口（UTC）：
    - quarter: 当前季度
    - current: 当前季度至今
    - last_quarter: 上一季度
    """
    now_sh = datetime.now(SH_TZ)
    quarter_start_month = (int((now_sh.month - 1) / 3) * 3) + 1
    mode = str(expected_mode or "").strip()

    if mode == "last_quarter":
        if quarter_start_month == 1:
            start_year = now_sh.year - 1
            start_month = 10
            next_q_start_local = datetime(now_sh.year, 1, 1, 0, 0, 0, tzinfo=SH_TZ)
        else:
            start_year = now_sh.year
            start_month = quarter_start_month - 3
            next_q_start_local = datetime(now_sh.year, quarter_start_month, 1, 0, 0, 0, tzinfo=SH_TZ)
        start_local = datetime(start_year, start_month, 1, 0, 0, 0, tzinfo=SH_TZ)
        end_local = next_q_start_local - timedelta(seconds=1)
        return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)

    start_local = datetime(now_sh.year, quarter_start_month, 1, 0, 0, 0, tzinfo=SH_TZ)
    if quarter_start_month == 10:
        next_q_start_local = datetime(now_sh.year + 1, 1, 1, 0, 0, 0, tzinfo=SH_TZ)
    else:
        next_q_start_local = datetime(now_sh.year, quarter_start_month + 3, 1, 0, 0, 0, tzinfo=SH_TZ)
    if mode == "current":
        end_local = now_sh
    else:
        end_local = next_q_start_local - timedelta(seconds=1)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def _group_detail_rows(team_id_value: str, expected_mode: str = "quarter"):
    from db.engine import SessionLocal
    from db.orm import ProjectTask, ProjectTaskDetail, ProjectTaskOverdueDetail, UserCharacter as DbUserCharacter

    # 当前先与个人工时一致：使用配置中的首个 projectId 作为统计项目。
    projectids = get_config_projectids() or {}
    project_id = ""
    if isinstance(projectids, dict) and projectids:
        project_id = str(next(iter(projectids.values())) or "").strip()

    start_dt, end_dt = _current_quarter_utc_range(expected_mode=expected_mode)
    expected_out = workdays_in_range_service(
        {
            "start_time": start_dt.isoformat(),
            "end_time": end_dt.isoformat(),
            "compensatoryDays": 0,
        }
    )
    quarter_expected_days = float(((expected_out.get("data") or {}).get("effective_workday_count")) or 0.0)
    coeff_out = get_workhour_character_coefficients_service() or {}
    coeff_map = coeff_out.get("workhour_character_coefficients") or {}

    session = SessionLocal()
    try:
        members = (
            session.query(DbUserCharacter)
            .filter(DbUserCharacter.team_id == str(team_id_value))
            .order_by(DbUserCharacter.user_id.asc())
            .all()
        )

        rows = []
        for m in members:
            uid = str(getattr(m, "user_id", "") or "").strip()
            if not uid:
                continue
            name = str(getattr(m, "name", "") or uid)
            role_label = _member_role_label_from_user_character(
                getattr(m, "character", 1),
                getattr(m, "is_nav_lead", False),
                getattr(m, "is_servo_lead", False),
            )
            member_character = int(getattr(m, "character", 1) or 1)
            coefficient = float(coeff_map.get(str(member_character), 1.0) or 1.0)
            expected_effective_hours = quarter_expected_days * coefficient

            b_base = (
                session.query(ProjectTaskDetail)
                .join(
                    ProjectTask,
                    and_(
                        ProjectTask.project_id == ProjectTaskDetail.project_id,
                        ProjectTask.task_id == ProjectTaskDetail.task_id,
                    ),
                )
                .filter(ProjectTaskDetail.query_user_id == uid)
                .filter(ProjectTask.due_date != None)  # noqa: E711
                .filter(ProjectTask.due_date >= start_dt)
                .filter(ProjectTask.due_date <= end_dt)
            )
            if project_id:
                b_base = b_base.filter(ProjectTaskDetail.project_id == project_id)

            scheduled_total = float(
                b_base.with_entities(func.coalesce(func.sum(ProjectTaskDetail.work_hour), 0.0)).scalar() or 0.0
            )
            completed_total = float(
                b_base.filter(ProjectTaskDetail.task_flow_status_id == 4)
                .with_entities(func.coalesce(func.sum(ProjectTaskDetail.work_hour), 0.0))
                .scalar()
                or 0.0
            )

            c_base = (
                session.query(ProjectTaskOverdueDetail)
                .join(
                    ProjectTask,
                    and_(
                        ProjectTask.project_id == ProjectTaskOverdueDetail.project_id,
                        ProjectTask.task_id == ProjectTaskOverdueDetail.task_id,
                    ),
                )
                .filter(ProjectTaskOverdueDetail.query_user_id == uid)
            )
            if project_id:
                c_base = c_base.filter(ProjectTaskOverdueDetail.project_id == project_id)
            overdue_effective_total = float(
                c_base.with_entities(func.coalesce(func.sum(ProjectTaskOverdueDetail.work_hour), 0.0)).scalar() or 0.0
            )
            overdue_completed_total = float(
                c_base.filter(ProjectTaskOverdueDetail.task_flow_status_id == 4)
                .with_entities(func.coalesce(func.sum(ProjectTaskOverdueDetail.work_hour), 0.0))
                .scalar()
                or 0.0
            )

            allocation_delta = scheduled_total - expected_effective_hours
            completion_delta = completed_total - expected_effective_hours

            rows.append(
                {
                    "name": name,
                    "role": role_label,
                    "quarterExpectedHours": round(expected_effective_hours, 2),
                    "workdayCount": round(quarter_expected_days, 2),
                    "character": member_character,
                    "coefficient": coefficient,
                    "scheduledHours": round(scheduled_total, 2),
                    "completedHours": round(completed_total, 2),
                    "overdueEffectiveHours": round(overdue_effective_total, 2),
                    "overdueCompletedHours": round(overdue_completed_total, 2),
                    "allocationDelta": round(allocation_delta, 2),
                    "completionDelta": round(completion_delta, 2),
                    # 兼容当前前端 TeamDetailDashboard 的缩放字段
                    "hours": round(scheduled_total, 2),
                }
            )
        return {
            "rows": rows,
            "quarterRange": {
                "startTime": start_dt.isoformat(),
                "endTime": end_dt.isoformat(),
            },
            "projectId": project_id,
        }
    finally:
        session.close()


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
        "workdayCount": 0.0,
        "expectedEffectiveDays": 0.0,
        "expectedCoefficient": 1.0,
        "calendarSource": "",
        "timezone": "",
    }

    role = str((user or {}).get("role") or "").strip().lower()
    user_id = str((user or {}).get("user_id") or "").strip()
    user_name = str((user or {}).get("name") or "").strip()
    coeff_out = get_workhour_character_coefficients_service() or {}
    workhour_character_coefficients = (coeff_out.get("workhour_character_coefficients") or {})

    member_options = []
    if role in {"manager", "admin"}:
        all_members = _load_user_character_members()
        member_options = [{"id": "ALL", "name": "全部人员", "team": "全部", "teamId": ""}] + all_members
    elif user_id:
        member_options = [{
            "id": user_id,
            "name": user_name or user_id,
            "userId": user_id,
            "character": int((user or {}).get("character", 1) or 1),
            "team": str((user or {}).get("team") or ""),
            "teamId": str((user or {}).get("teamId") or ""),
        }]
    elif user_name:
        # 兼容：极端情况下 auth_user 没有 user_id，仍保证页面可用
        member_options = [{"id": user_name, "name": user_name, "team": str((user or {}).get("team") or "")}]

    selected_target = str(target or "").strip() or "ALL"
    if selected_target == "ALL":
        target_label = "全部人员"
    else:
        hit = next((x for x in member_options if str(x.get("id") or "") == selected_target), None)
        target_label = str((hit or {}).get("name") or selected_target)
    dashboard["targetLabel"] = target_label

    # 个人工时页口径：
    # 后端仅返回区间法定工作日（不扣调休），前端再按 (工作日-调休)*系数 动态计算预期值。
    target_character = 1
    target_hit = next((x for x in member_options if str(x.get("id") or "") == selected_target), None)
    if target_hit and target_hit.get("character") is not None:
        try:
            target_character = int(target_hit.get("character"))
        except Exception:
            target_character = 1
    elif (user or {}).get("character") is not None:
        try:
            target_character = int((user or {}).get("character"))
        except Exception:
            target_character = 1

    coeff = float(workhour_character_coefficients.get(str(target_character), 1.0) or 1.0)
    wd_out = workdays_in_range_service(
        {
            "start_time": start_time,
            "end_time": end_time,
            "compensatoryDays": 0,
        }
    ) or {}
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
            {
                "month": str(item.get("month") or ""),
                "total": float(item.get("day") or 0),
            }
            for item in month_workdays
            if str(item.get("month") or "").strip()
        ],
        "dashboard": dashboard,
        "workhourCharacterCoefficients": workhour_character_coefficients,
        "memberOptions": member_options,
        "selectedTarget": selected_target,
    }


@dashboard_bp.route("/personal-hours", methods=["GET"])
def personal_hours():
    user = _require_login()
    if not user:
        return _fail("unauthenticated", code=401, data={})

    target = (request.args.get("target") or user.get("user_id") or user.get("name") or "").strip()
    if not target:
        target = "ALL"
    return _ok(_build_default_personal_hours_payload(user, target))


@dashboard_bp.route("/personal-hours/members", methods=["GET"])
def personal_hours_members():
    user = _require_login()
    if not user:
        return _fail("unauthenticated", code=401, data={})

    target = (user.get("user_id") or user.get("name") or "").strip() or "ALL"
    out = _build_default_personal_hours_payload(user, target)
    return _ok(
        {
            "memberOptions": out.get("memberOptions") or [],
            "selectedTarget": out.get("selectedTarget") or target,
        }
    )


@dashboard_bp.route("/personal-hours/query", methods=["POST"])
def personal_hours_query():
    user = _require_login()
    if not user:
        return _fail("unauthenticated", code=401, data={})

    payload = request.get_json(silent=True) or {}
    target = str(payload.get("target") or user.get("user_id") or user.get("name") or "").strip() or "ALL"
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
    # 使用前端传入的查询区间重新计算后端口径工作日（不扣调休）
    start_date = str((out.get("dashboard") or {}).get("defaultRange", {}).get("startDate") or "")
    end_date = str((out.get("dashboard") or {}).get("defaultRange", {}).get("endDate") or "")
    coeff_map = out.get("workhourCharacterCoefficients") or {}
    member_options = out.get("memberOptions") or []
    target_character = 1
    target_hit = next((x for x in member_options if str(x.get("id") or "") == target), None)
    if target_hit and target_hit.get("character") is not None:
        try:
            target_character = int(target_hit.get("character"))
        except Exception:
            target_character = 1
    elif (user or {}).get("character") is not None:
        try:
            target_character = int((user or {}).get("character"))
        except Exception:
            target_character = 1
    coeff = float(coeff_map.get(str(target_character), 1.0) or 1.0)
    wd_out = workdays_in_range_service(
        {
            "start_time": start_date,
            "end_time": end_date,
            "compensatoryDays": 0,
        }
    ) or {}
    wd_data = wd_out.get("data") or {}
    raw_workday_count = float(wd_data.get("workday_count") or 0.0)
    month_workdays = wd_data.get("month_workdays") or []
    out["dashboard"]["workdayCount"] = round(raw_workday_count, 2)
    out["dashboard"]["expectedCoefficient"] = coeff
    out["dashboard"]["expectedEffectiveDays"] = round(raw_workday_count * coeff, 2)
    out["dashboard"]["calendarSource"] = str(wd_data.get("calendar_source") or "")
    out["dashboard"]["timezone"] = str(wd_data.get("timezone") or "")
    out["trend"] = [
        {
            "month": str(item.get("month") or ""),
            "total": float(item.get("day") or 0),
        }
        for item in month_workdays
        if str(item.get("month") or "").strip()
    ]
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


@dashboard_bp.route("/nav-team-detail", methods=["GET"])
def nav_team_detail():
    user = _require_login()
    if not user:
        return _fail("unauthenticated", code=401, data={})
    expected_mode = str(request.args.get("expected") or "quarter").strip()
    if expected_mode not in {"quarter", "current", "last_quarter"}:
        expected_mode = "quarter"
    return _ok(_group_detail_rows("0", expected_mode=expected_mode))


@dashboard_bp.route("/integration-team-detail", methods=["GET"])
def integration_team_detail():
    user = _require_login()
    if not user:
        return _fail("unauthenticated", code=401, data={})
    expected_mode = str(request.args.get("expected") or "quarter").strip()
    if expected_mode not in {"quarter", "current", "last_quarter"}:
        expected_mode = "quarter"
    return _ok(_group_detail_rows("1", expected_mode=expected_mode))

