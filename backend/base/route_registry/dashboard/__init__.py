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
