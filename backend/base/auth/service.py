from typing import Any, Dict, Optional, Tuple

from base.dingtalk_client import (
    exchange_dingtalk_auth_code,
    get_dingtalk_user_info,
    get_userid_by_unionid,
)
from base.organization.constants import (
    ROLE_LABELS as JOB_ROLE_LABELS,
    TEAM_LABELS,
    stable_role_code,
    stable_team_code,
)


ROLE_LABELS = {
    "employee": "员工",
    "manager": "主管",
    "admin": "管理员",
}

ROLE_DATA_SCOPE = {
    "employee": "self",
    "manager": "team",
    "admin": "all",
}

ROLE_HOME_PATH = {
    "employee": "/employee/personal-hours",
    "manager": "/manager/nav-team-detail",
    "admin": "/manager/department-overview",
}

ROLE_PERMISSION_CODES = {
    "employee": [
        "page.personal_hours",
        "page.performance",
        "page.ai_analysis",
    ],
    "manager": [
        "page.nav_team_detail",
        "page.integration_team_detail",
        "page.application_team",
        "page.app_three_team",
        "page.personal_hours",
        "page.performance",
        "page.ai_analysis",
        "page.workday_costhour",
        "button.export_report",
        "button.view_ai_suggestions",
        "button.review_member",
    ],
    "admin": [
        "page.department_overview",
        "page.nav_team_detail",
        "page.integration_team_detail",
        "page.application_team",
        "page.app_three_team",
        "page.personal_hours",
        "page.performance",
        "page.ai_analysis",
        "page.permissions",
        "page.prototype",
        "page.workday_costhour",
        "button.export_report",
        "button.view_ai_suggestions",
        "button.configure_role",
        "button.configure_data_scope",
        "button.review_member",
    ],
}


def _derive_role_and_access(
    job_role_code: str,
    is_nav_lead: bool,
    is_servo_lead: bool,
    is_p3_lead: bool = False,
) -> Dict[str, Any]:
    """
    角色/权限细分规则：
    1) SYSTEM_ADMIN -> 内置管理员 admin，无需依赖 lead 标记
    2) TEAM_LEAD:
       - is_nav_lead && is_servo_lead -> admin
       - is_servo_lead -> manager（仅对接组分栏）
       - is_nav_lead -> manager（仅导航组分栏）
       - 两者都不是 -> manager（保留默认 manager 权限）
    3) 其他岗位 -> employee
    """
    role_code = stable_role_code(job_role_code)
    if role_code == "SYSTEM_ADMIN":
        return {
            "role": "admin",
            "permissionCodes": [
                "page.department_overview",
                "page.nav_team_detail",
                "page.integration_team_detail",
                "page.application_team",
                "page.app_three_team",
                "page.personal_hours",
                "page.performance",
                "page.ai_analysis",
                "page.permissions",
                "page.workday_costhour",
                "button.export_report",
                "button.view_ai_suggestions",
                "button.configure_role",
                "button.configure_data_scope",
                "button.review_member",
            ],
            "homePath": "/manager/department-overview",
            "dataScope": "all",
        }

    if role_code != "TEAM_LEAD":
        return {"role": "employee"}

    nav = bool(is_nav_lead)
    servo = bool(is_servo_lead)
    p3 = bool(is_p3_lead)
    if nav and servo:
        return {"role": "admin"}

    if nav and not servo:
        return {
            "role": "manager",
            "permissionCodes": [
                "page.nav_team_detail",
                "page.application_team",
                "page.app_three_team",
                "page.personal_hours",
                "page.performance",
                "page.ai_analysis",
                "page.workday_costhour",
                "button.export_report",
                "button.view_ai_suggestions",
                "button.review_member",
            ],
            "homePath": "/manager/nav-team-detail",
            "dataScope": "team",
        }

    if servo and not nav:
        return {
            "role": "manager",
            "permissionCodes": [
                "page.integration_team_detail",
                "page.application_team",
                "page.app_three_team",
                "page.personal_hours",
                "page.performance",
                "page.ai_analysis",
                "page.workday_costhour",
                "button.export_report",
                "button.view_ai_suggestions",
                "button.review_member",
            ],
            "homePath": "/manager/integration-team-detail",
            "dataScope": "team",
        }

    if p3:
        return {
            "role": "manager",
            "permissionCodes": [
                "page.app_three_team",
                "page.personal_hours",
                "page.performance",
                "page.ai_analysis",
                "page.workday_costhour",
                "button.export_report",
                "button.view_ai_suggestions",
                "button.review_member",
            ],
            "homePath": "/manager/app-three-team",
            "dataScope": "team",
        }

    return {"role": "manager"}


def _get_user_character_row(external_ids: Tuple[str, ...]):
    """
    用钉钉侧标识去找本地 user_character.user_id。
    约定：user_character.user_id 存的是钉钉 userId（通常为数字串）。
    """
    from base.db.engine import SessionLocal
    from base.db.orm import UserCharacter as DbUserCharacter

    session = SessionLocal()
    try:
        for uid in external_ids:
            uid = str(uid or "").strip()
            if not uid:
                continue
            row = session.query(DbUserCharacter).filter(DbUserCharacter.user_id == uid).first()
            if row:
                return row
        return None
    finally:
        session.close()


def _normalize_profile(base: Dict[str, Any], dingtalk_user: Dict[str, Any]) -> Dict[str, Any]:
    role = str(base.get("role") or "employee").strip().lower()
    if role not in {"employee", "manager", "admin"}:
        role = "employee"

    name = str(base.get("name") or dingtalk_user.get("nick") or "未命名用户")
    team_code = str(base.get("teamCode") or "").strip().upper()
    job_role_code = str(base.get("jobRoleCode") or "").strip().upper()
    permission_codes = base.get("permissionCodes")
    if not isinstance(permission_codes, list) or not permission_codes:
        permission_codes = ROLE_PERMISSION_CODES[role]

    profile = {
        "id": str(base.get("id") or (dingtalk_user.get("unionId") or dingtalk_user.get("openId") or dingtalk_user.get("userid") or "")),
        "user_id": str(base.get("user_id") or dingtalk_user.get("userid") or ""),
        "name": name,
        "teamCode": team_code,
        "teamName": str(base.get("teamName") or TEAM_LABELS.get(team_code, "未分组")),
        "jobRoleCode": job_role_code,
        "jobRoleName": str(base.get("jobRoleName") or JOB_ROLE_LABELS.get(job_role_code, "未设置")),
        "role": role,
        "roleLabel": ROLE_LABELS[role],
        "dataScope": str(base.get("dataScope") or ROLE_DATA_SCOPE[role]),
        "permissionCodes": permission_codes,
        "homePath": str(base.get("homePath") or ROLE_HOME_PATH[role]),
        "dingtalkUserId": str(
            dingtalk_user.get("unionId")
            or dingtalk_user.get("openId")
            or dingtalk_user.get("userid")
            or ""
        ),
    }
    return profile


def resolve_user_profile(dingtalk_user: Dict[str, Any]) -> Dict[str, Any]:
    union_id = str(dingtalk_user.get("unionId") or "").strip()
    open_id = str(dingtalk_user.get("openId") or "").strip()
    user_id = str(dingtalk_user.get("userid") or "").strip()

    # 当前规则：岗位决定基础角色，lead 标记决定主管的数据范围。
    c_row = _get_user_character_row((user_id, union_id, open_id))
    if c_row is None:
        return {"ok": False, "error": "user is not in the organization roster"}
    job_role_code = stable_role_code(getattr(c_row, "job_role_code", None))
    if not job_role_code:
        job_role_code = "SOFTWARE_ENGINEER"
    is_nav_lead = bool(getattr(c_row, "is_nav_lead", False)) if c_row else False
    is_servo_lead = bool(getattr(c_row, "is_servo_lead", False)) if c_row else False
    is_p3_lead = bool(getattr(c_row, "is_p3_lead", False)) if c_row else False
    derived = _derive_role_and_access(job_role_code, is_nav_lead, is_servo_lead, is_p3_lead)
    role = str(derived.get("role") or "employee")

    base: Dict[str, Any] = {
        "role": role,
        "permissionCodes": derived.get("permissionCodes"),
        "homePath": derived.get("homePath"),
        "dataScope": derived.get("dataScope"),
        # 如果库里有人名/组别信息，就优先用库里的；否则回退钉钉 nick / 未分组
        "name": getattr(c_row, "name", None) if c_row else None,
        "teamCode": stable_team_code(getattr(c_row, "team_code", None)) if c_row else "",
        "jobRoleCode": job_role_code,
    }

    return {"ok": True, "source": "user_character", "profile": _normalize_profile(base, dingtalk_user)}


def authenticate_local_user(user_id: str, password: str) -> Dict[str, Any]:
    """离线模式：用本地 user_character 表中的 user_id + 密码登录。

    密码规则：组长/管理员使用管理密码，其他岗位使用员工密码。
    登录成功直接返回 profile，不走钉钉 API。
    """
    user_id = str(user_id or "").strip()
    password = str(password or "").strip()

    if not user_id or not password:
        return {"ok": False, "error": "missing user_id or password"}

    from base.db.engine import SessionLocal
    from base.db.orm import UserCharacter as DbUserCharacter

    session = SessionLocal()
    try:
        row = session.query(DbUserCharacter).filter(DbUserCharacter.user_id == user_id).first()
        if not row:
            return {"ok": False, "error": f"user not found: {user_id}"}

        job_role_code = stable_role_code(getattr(row, "job_role_code", None)) or "SOFTWARE_ENGINEER"

        if job_role_code in {"TEAM_LEAD", "SYSTEM_ADMIN"}:
            expected_password = "JZ123456"
        else:
            expected_password = "123456"

        if password != expected_password:
            return {"ok": False, "error": "invalid password"}

        is_nav_lead = bool(getattr(row, "is_nav_lead", False))
        is_servo_lead = bool(getattr(row, "is_servo_lead", False))
        is_p3_lead = bool(getattr(row, "is_p3_lead", False))
        derived = _derive_role_and_access(job_role_code, is_nav_lead, is_servo_lead, is_p3_lead)
        role = str(derived.get("role") or "employee")
        team_code = stable_team_code(getattr(row, "team_code", None))
        name = str(getattr(row, "name", "") or row.user_id)

        base: Dict[str, Any] = {
            "role": role,
            "permissionCodes": derived.get("permissionCodes"),
            "homePath": derived.get("homePath"),
            "dataScope": derived.get("dataScope"),
            "name": name,
            "teamCode": team_code,
            "jobRoleCode": job_role_code,
            "id": row.user_id,
            "user_id": row.user_id,
        }

        dingtalk_user = {
            "nick": name,
            "userid": row.user_id,
            "unionId": getattr(row, "union_id", "") or "",
            "openId": "",
        }

        profile = _normalize_profile(base, dingtalk_user)
        return {"ok": True, "profile": profile, "source": "local"}
    finally:
        session.close()


def authenticate_dingtalk_user(auth_code: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Exchange a DingTalk auth code for a user profile.

    Args:
        auth_code: The authorization code from DingTalk OAuth /免登.
        payload: Optional extra parameters forwarded to the token exchange.

    Returns:
        Dict with ok=True and profile on success, or ok=False and error on failure.
    """
    auth_code = str(auth_code or "").strip()
    if not auth_code:
        return {"ok": False, "error": "missing auth code"}

    token_out = exchange_dingtalk_auth_code(auth_code, payload=payload or {})
    if not token_out.get("ok"):
        return {"ok": False, "error": str(token_out.get("error") or "failed to exchange auth code")}

    user_token = (token_out.get("data") or {}).get("accessToken")
    user_out = get_dingtalk_user_info(user_token)
    if not user_out.get("ok"):
        return {"ok": False, "error": str(user_out.get("error") or "failed to get dingtalk user info")}

    user_data = dict(user_out.get("data") or {})
    # Some login flows only return unionId/openId without userId.
    # Supplement with getUseridByUnionid so we can match local user_character.user_id.
    if not str(user_data.get("userid") or "").strip() and str(user_data.get("unionId") or "").strip():
        u2i_out = get_userid_by_unionid(user_data.get("unionId"))
        if u2i_out.get("ok"):
            user_data["userid"] = (u2i_out.get("data") or {}).get("userid")

    profile_out = resolve_user_profile(user_data)
    if not profile_out.get("ok"):
        return {"ok": False, "error": str(profile_out.get("error") or "unauthorized account")}

    # 回填 unionId 到 user_character，后续 AI 分析等场景直接查表
    _save_union_id_to_user_character(user_data)

    return {"ok": True, "profile": profile_out.get("profile")}


def _save_union_id_to_user_character(user_data: Dict[str, Any]) -> None:
    """登录时将 dingtalk 返回的 unionId 写入 user_character 表。"""
    user_id = str(user_data.get("userid") or "").strip()
    union_id = str(user_data.get("unionId") or "").strip()
    if not user_id or not union_id:
        return

    from base.db.engine import SessionLocal
    from base.db.orm import UserCharacter as DbUserCharacter

    session = SessionLocal()
    try:
        row = session.query(DbUserCharacter).filter(DbUserCharacter.user_id == user_id).first()
        if row and not row.union_id:
            row.union_id = union_id
            session.commit()
    finally:
        session.close()
