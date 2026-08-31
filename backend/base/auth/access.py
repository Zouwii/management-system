"""Shared server-side session and permission checks for business routes."""

from typing import Any, Callable, Dict, Iterable, Optional, Tuple

from flask import session


def current_user() -> Optional[Dict[str, Any]]:
    user = session.get("auth_user")
    return user if isinstance(user, dict) else None


def require_access(
    fail: Callable[..., Any],
    *,
    any_permissions: Iterable[str] = (),
    any_roles: Iterable[str] = (),
) -> Tuple[Optional[Dict[str, Any]], Optional[Any]]:
    """Return the session user or a ready-to-return 401/403 response."""
    user = current_user()
    if not user:
        return None, fail("unauthenticated", code=401, data={})

    required_permissions = {str(code).strip() for code in any_permissions if str(code).strip()}
    if required_permissions:
        user_permissions = {
            str(code).strip()
            for code in (user.get("permissionCodes") or [])
            if str(code).strip()
        }
        if required_permissions.isdisjoint(user_permissions):
            return None, fail("forbidden", code=403, data={})

    required_roles = {str(role).strip().lower() for role in any_roles if str(role).strip()}
    if required_roles and str(user.get("role") or "").strip().lower() not in required_roles:
        return None, fail("forbidden", code=403, data={})

    return user, None
