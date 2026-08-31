"""Stable organization and job-role codes used by roster policies.

Legacy numeric values are accepted only by the explicit migration helpers.
Runtime business code must use the stable string codes below.
"""

from typing import Dict, Tuple


TEAM_ORDER: Tuple[str, ...] = ("NAV", "INTEGRATION", "ALGORITHM", "APP_THREE")
TEAM_LABELS: Dict[str, str] = {
    "NAV": "导航组",
    "INTEGRATION": "对接组",
    "ALGORITHM": "算法组",
    "APP_THREE": "应用三组",
}

ROLE_LABELS: Dict[str, str] = {
    "TEAM_LEAD": "组长",
    "SOFTWARE_ENGINEER": "软件开发工程师",
    "SOFTWARE_APPLICATION_ENGINEER": "软件应用工程师",
    "APPLICATION_ENGINEER": "应用工程师",
    "ALGORITHM_ENGINEER": "算法工程师",
    "INTERN": "实习生",
    "SYSTEM_ADMIN": "管理员",
}

LEGACY_TEAM_ID_TO_CODE: Dict[str, str] = {
    "0": "NAV",
    "1": "INTEGRATION",
    "2": "ALGORITHM",
    # Do not normalize legacy numeric team_id=3 here. It historically meant
    # the old application-team experiment, while APP_THREE is a new formal
    # team. The explicit migration resolves that ambiguity.
    "nav": "NAV",
    "navigation": "NAV",
    "导航组": "NAV",
    "servo": "INTEGRATION",
    "service": "INTEGRATION",
    "integration": "INTEGRATION",
    "对接组": "INTEGRATION",
    "algorithm": "ALGORITHM",
    "算法组": "ALGORITHM",
    "app_three": "APP_THREE",
    "应用三组": "APP_THREE",
}

LEGACY_CHARACTER_TO_ROLE: Dict[str, str] = {
    "0": "TEAM_LEAD",
    "1": "SOFTWARE_ENGINEER",
    "2": "SOFTWARE_APPLICATION_ENGINEER",
    "3": "APPLICATION_ENGINEER",
    "4": "ALGORITHM_ENGINEER",
    "5": "INTERN",
    "9": "SYSTEM_ADMIN",
    "组长": "TEAM_LEAD",
    "软件开发工程师": "SOFTWARE_ENGINEER",
    "软件应用工程师": "SOFTWARE_APPLICATION_ENGINEER",
    "应用工程师": "APPLICATION_ENGINEER",
    "算法工程师": "ALGORITHM_ENGINEER",
    "实习生": "INTERN",
    "管理员": "SYSTEM_ADMIN",
}

# A policy is deliberately data-shaped rather than spread through page code.
# The first version is kept in source control; it can later be backed by an
# admin-managed table without changing RosterService callers.
SCOPE_POLICIES: Dict[str, Dict[str, Tuple[str, ...]]] = {
    "DEPARTMENT_EFFECTIVE_HOURS": {
        "teams": ("NAV", "INTEGRATION"),
        "roles": (),
    },
    "WORKDAY_COST": {
        "teams": ("NAV", "INTEGRATION", "ALGORITHM"),
        "roles": (),
    },
    "ATTENDANCE": {
        "teams": ("NAV", "INTEGRATION", "ALGORITHM"),
        "roles": (),
    },
    "QUARTER_PERFORMANCE": {
        "teams": ("NAV", "INTEGRATION"),
        "roles": (),
    },
    "APPLICATION_TEAM_VIEW": {
        "teams": ("NAV",),
        "roles": ("APPLICATION_ENGINEER",),
    },
    "APP_THREE_TEAM_VIEW": {
        "teams": ("APP_THREE",),
        "roles": (),
    },
    "TB_TASK_SYNC": {
        "teams": ("NAV", "INTEGRATION"),
        "roles": (),
    },
}


def normalize_team_code(value: object) -> str:
    """Return a stable team code for a legacy ID, label, or new code."""
    raw = "" if value is None else str(value).strip()
    if not raw:
        return ""
    upper = raw.upper()
    if upper in TEAM_LABELS:
        return upper
    return LEGACY_TEAM_ID_TO_CODE.get(raw.lower(), "")


def normalize_role_code(value: object) -> str:
    """Return a stable role code for a legacy character or new code."""
    raw = "" if value is None else str(value).strip()
    if not raw:
        return ""
    upper = raw.upper()
    if upper in ROLE_LABELS:
        return upper
    return LEGACY_CHARACTER_TO_ROLE.get(raw, "")


def stable_team_code(value: object) -> str:
    """Validate and return a stable runtime team code."""
    raw = "" if value is None else str(value).strip().upper()
    return raw if raw in TEAM_LABELS else ""


def stable_role_code(value: object) -> str:
    """Validate and return a stable runtime job-role code."""
    raw = "" if value is None else str(value).strip().upper()
    return raw if raw in ROLE_LABELS else ""
