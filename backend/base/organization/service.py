"""Unified people roster resolution for all business pages and sync jobs."""

from typing import Any, Dict, List, Optional, Set

from base.db.engine import SessionLocal
from base.db.orm import UserCharacter

from .constants import (
    ROLE_LABELS,
    TEAM_LABELS,
    TEAM_ORDER,
    stable_role_code,
    stable_team_code,
)
from .scopes import get_scope_policy


def _row_team_code(row: Any) -> str:
    return stable_team_code(getattr(row, "team_code", None))


def _row_role_code(row: Any) -> str:
    return stable_role_code(getattr(row, "job_role_code", None))


def _row_member(row: Any) -> Dict[str, Any]:
    team_code = _row_team_code(row)
    role_code = _row_role_code(row)
    return {
        "userId": str(getattr(row, "user_id", "") or "").strip(),
        "userName": str(getattr(row, "name", "") or getattr(row, "user_id", "") or "").strip(),
        "teamCode": team_code,
        "teamName": TEAM_LABELS.get(team_code, team_code or "未分组"),
        "jobRoleCode": role_code,
        "jobRoleName": ROLE_LABELS.get(role_code, role_code or "未设置"),
        "isTeamLead": role_code in {"TEAM_LEAD", "SYSTEM_ADMIN"},
    }


def _scope_matches(row: Any, scope_code: str, team_code: Optional[str] = None) -> bool:
    policy = get_scope_policy(scope_code)
    row_team = _row_team_code(row)
    row_role = _row_role_code(row)
    if row_team not in policy["teams"]:
        return False
    if policy["roles"] and row_role not in policy["roles"]:
        return False
    # System/admin accounts are not business roster members unless a future
    # policy explicitly lists SYSTEM_ADMIN as its role.
    if not policy["roles"] and row_role == "SYSTEM_ADMIN":
        return False
    if team_code and row_team != stable_team_code(team_code):
        return False
    return True


def _load_rows(session_factory=None) -> List[Any]:
    session = (session_factory or SessionLocal)()
    try:
        return session.query(UserCharacter).order_by(UserCharacter.user_id.asc()).all()
    finally:
        session.close()


def list_scope_teams(scope_code: str) -> Dict[str, Any]:
    """Return configured team options for a scope, including empty teams."""
    policy = get_scope_policy(scope_code)
    teams = [
        {
            "code": code,
            "name": TEAM_LABELS[code],
            "teamCode": code,
            "teamName": TEAM_LABELS[code],
        }
        for code in TEAM_ORDER
        if code in policy["teams"]
    ]
    return {"scopeCode": str(scope_code).strip().upper(), "teams": teams}


def list_all_members(*, session_factory=None) -> List[Dict[str, Any]]:
    """Return the database roster without applying a business Scope."""
    return [
        _row_member(row)
        for row in _load_rows(session_factory)
        if str(getattr(row, "user_id", "") or "").strip()
    ]


def resolve_sync_operator_id(*, session_factory=None) -> str:
    """Choose a stable sync operator from the database roster."""
    members = list_all_members(session_factory=session_factory)
    for preferred_role in ("SYSTEM_ADMIN", "TEAM_LEAD"):
        for member in members:
            if member.get("jobRoleCode") == preferred_role:
                return str(member.get("userId") or "").strip()
    return str(members[0].get("userId") or "").strip() if members else ""


def list_scope_members(
    scope_code: str,
    team_code: Optional[str] = None,
    *,
    session_factory=None,
) -> List[Dict[str, Any]]:
    """Resolve members using one scope policy and optional team filter."""
    # Validate the scope before validating an optional filter so callers get a
    # consistent error for a misspelled scope.
    get_scope_policy(scope_code)
    normalized_team = str(team_code or "").strip().upper() if team_code else None
    if normalized_team and normalized_team not in TEAM_LABELS:
        raise ValueError("unknown team: {}".format(team_code))
    members = [
        _row_member(row)
        for row in _load_rows(session_factory)
        if _scope_matches(row, scope_code, normalized_team)
    ]
    return members


def list_scope_member_ids(
    scope_code: str,
    team_code: Optional[str] = None,
    *,
    session_factory=None,
) -> Set[str]:
    return {
        str(member["userId"]).strip()
        for member in list_scope_members(scope_code, team_code, session_factory=session_factory)
        if str(member.get("userId") or "").strip()
    }


def is_person_in_scope(user_id: str, scope_code: str) -> bool:
    target = str(user_id or "").strip()
    if not target:
        return False
    return any(member["userId"] == target for member in list_scope_members(scope_code))


class RosterService:
    """Small service facade for dependency injection in routes and jobs.

    Module-level functions remain available for the current callers; the
    facade gives future business modules one stable object to depend on.
    """

    def list_scope_teams(self, scope_code: str) -> Dict[str, Any]:
        return list_scope_teams(scope_code)

    def list_scope_members(self, scope_code: str, team_code: Optional[str] = None) -> List[Dict[str, Any]]:
        return list_scope_members(scope_code, team_code)

    def list_scope_member_ids(self, scope_code: str, team_code: Optional[str] = None) -> Set[str]:
        return list_scope_member_ids(scope_code, team_code)

    def is_person_in_scope(self, user_id: str, scope_code: str) -> bool:
        return is_person_in_scope(user_id, scope_code)
