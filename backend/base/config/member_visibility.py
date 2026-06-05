from __future__ import annotations

from typing import Any, Mapping


def to_character(value: Any, default: int = 0) -> int:
    """安全解析 character，避免 0 被误判为缺省。"""
    try:
        if value is None:
            return default
        if isinstance(value, bool):
            return int(value)
        return int(str(value).strip())
    except Exception:
        return default


def is_dual_team_admin(member: Mapping[str, Any] | None) -> bool:
    """
    统一管理员识别规则：
    仅当 character=0 且同时是 nav+servo lead 时，视为双组管理员。
    """
    m = member or {}
    return (
        to_character(m.get("character"), default=0) == 0
        and bool(m.get("isNavLead"))
        and bool(m.get("isServoLead"))
    )


def should_hide_member_in_selector(member: Mapping[str, Any] | None) -> bool:
    """成员下拉过滤规则入口。"""
    return is_dual_team_admin(member)

