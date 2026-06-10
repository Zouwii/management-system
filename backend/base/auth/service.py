from typing import Any, Dict, Optional, Tuple

from base.dingtalk_client import (
    exchange_dingtalk_auth_code,
    get_dingtalk_user_info,
    get_userid_by_unionid,
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


def _get_profile_from_db(_external_id: str, _dingtalk_user: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    # phase-2 预留：后续迁移到 DB RBAC 时，在这里接入数据库查询。
    return None


def _role_from_character(character: int) -> str:
    """
    基础规则：
    - character == 0 -> 主管端（manager，后续再结合 lead 标记细分权限）
    - character in {1,2,3} -> 员工端（employee）
    其余值默认 employee。
    """
    try:
        c = int(character)
    except Exception:
        c = 0
    return "manager" if c == 0 else "employee"


def _derive_role_and_access(character: int, is_nav_lead: bool, is_servo_lead: bool) -> Dict[str, Any]:
    """
    角色/权限细分规则：
    1) character == 0:
       - is_nav_lead && is_servo_lead -> admin
       - is_servo_lead -> manager（仅对接组分栏）
       - is_nav_lead -> manager（仅导航组分栏）
       - 两者都不是 -> manager（保留默认 manager 权限）
    2) character in {1,2,3} -> employee
    3) 其它 -> employee
    """
    role = _role_from_character(character)
    if role != "manager":
        return {"role": role}

    nav = bool(is_nav_lead)
    servo = bool(is_servo_lead)
    if nav and servo:
        return {"role": "admin"}

    if nav and not servo:
        return {
            "role": "manager",
            "permissionCodes": [
                "page.nav_team_detail",
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

    return {"role": "manager"}


def _team_name_from_team_id(team_id_value: Any) -> Optional[str]:
    """
    team_id 规则：
    - 0 -> 导航组
    - 1 -> 对接组
    其余/空值返回 None（后续走默认“未分组”）。
    """
    if team_id_value is None:
        return None
    val = str(team_id_value).strip()
    if val == "0":
        return "导航组"
    if val == "1":
        return "对接组"
    return None


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
    team = str(base.get("team") or "未分组")
    permission_codes = base.get("permissionCodes")
    if not isinstance(permission_codes, list) or not permission_codes:
        permission_codes = ROLE_PERMISSION_CODES[role]

    profile = {
        "id": str(base.get("id") or (dingtalk_user.get("unionId") or dingtalk_user.get("openId") or dingtalk_user.get("userid") or "")),
        "user_id": str(base.get("user_id") or dingtalk_user.get("userid") or ""),
        "character": int(base.get("character", 1) or 1),
        "name": name,
        "team": team,
        "teamId": str(base.get("teamId") or ""),
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

    # phase-2: DB RBAC 预留（如果后续你要接更完整的 user/role/permission 表）
    for external_id in (union_id, open_id, user_id):
        if not external_id:
            continue
        db_profile = _get_profile_from_db(external_id, dingtalk_user)
        if db_profile:
            return {"ok": True, "source": "db", "profile": _normalize_profile(db_profile, dingtalk_user)}

    # 当前规则：不走 auth_mapping 白名单；改为查 user_character.character 决定角色
    c_row = _get_user_character_row((user_id, union_id, open_id))
    raw_character = getattr(c_row, "character", None) if c_row else None
    if raw_character is None or str(raw_character).strip() == "":
        character = 1
        character_defaulted = True
    else:
        character = int(raw_character)
        character_defaulted = False
    is_nav_lead = bool(getattr(c_row, "is_nav_lead", False)) if c_row else False
    is_servo_lead = bool(getattr(c_row, "is_servo_lead", False)) if c_row else False
    derived = _derive_role_and_access(character, is_nav_lead, is_servo_lead)
    role = str(derived.get("role") or "employee")

    base: Dict[str, Any] = {
        "role": role,
        "permissionCodes": derived.get("permissionCodes"),
        "homePath": derived.get("homePath"),
        "dataScope": derived.get("dataScope"),
        "character": character,
        # 如果库里有人名/组别信息，就优先用库里的；否则回退钉钉 nick / 未分组
        "name": getattr(c_row, "name", None) if c_row else None,
        "team": _team_name_from_team_id(getattr(c_row, "team_id", None)) if c_row else None,
        "teamId": getattr(c_row, "team_id", "") if c_row else "",
    }

    return {"ok": True, "source": "user_character", "profile": _normalize_profile(base, dingtalk_user)}


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
