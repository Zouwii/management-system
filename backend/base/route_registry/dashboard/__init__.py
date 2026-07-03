"""Dashboard Blueprint and shared helpers.

The dashboard_bp uses prefix /api/dashboard and is registered directly
on the Flask app (not through the route_registry pattern).
"""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from flask import Blueprint, session

dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/api/dashboard")
SH_TZ = ZoneInfo("Asia/Shanghai")


def _ok(data):
    """Standard success JSON response."""
    return {"code": 200, "error": "", "data": data}, 200


def _fail(msg, code=400, data=None):
    """Standard error JSON response."""
    return {"code": code, "error": msg, "data": data if data is not None else {}}, code


def _require_login():
    """Return current auth_user from session, or None if not logged in."""
    return session.get("auth_user")


def _team_name_from_team_id(team_id_value):
    """Map team_id integer to Chinese team name."""
    if team_id_value is None:
        return "未分组"
    val = str(team_id_value).strip()
    if val == "0":
        return "导航组"
    if val == "1":
        return "对接组"
    return "未分组"


def _to_character(value, default: int = 0) -> int:
    """Safely parse character value to int, avoiding 0-or-1 ambiguity."""
    try:
        if value is None:
            return int(default)
        return int(value)
    except Exception:
        return int(default)


def _member_role_label_from_user_character(character_value, is_nav_lead, is_servo_lead):
    """Map character integer to Chinese role label.

    0=组长, 1=软件开发工程师, 2=软件应用工程师, 3=应用工程师, 4=算法工程师, 5=实习生
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
    if c == 5:
        return "实习生"
    return "软件开发工程师"


def _current_quarter_utc_range(expected_mode: str = "quarter"):
    """Calculate start/end UTC datetimes for a statistical window.

    Modes: 'quarter' (full quarter), 'current' (quarter-to-now), 'last_quarter'.
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


# Import route modules so they register on dashboard_bp
from workhour.personal import routes as _personal  # noqa: E402, F401
from workhour.team import routes as _team          # noqa: E402, F401
from . import performance_history as _perf_hist    # noqa: E402, F401
