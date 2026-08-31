"""Dashboard team detail routes.

Routes:
  GET /nav-team-detail           - Navigation team quarterly detail
  GET /integration-team-detail   - Integration team quarterly detail
  GET /application-team-detail   - Navigation application-engineer view
  GET /app-three-team-detail     - Application-three team quarterly detail
"""

from flask import request

from base.auth.access import require_access
from workhour.personal.aggregate import team_quarter_workhours_db_service
from base.dingtalk_client import get_config_projectids
from base.organization.service import list_scope_member_ids

from base.route_registry.dashboard import (
    _current_quarter_utc_range,
    _fail,
    _ok,
    dashboard_bp,
)


def _team_detail_handler(
    expected_mode: str,
    scope_code: str,
    team_code: str,
):
    """Build one team-detail response from stable Scope and team codes."""
    projectids = get_config_projectids() or {}
    project_id = ""
    if isinstance(projectids, dict) and projectids:
        project_id = str(next(iter(projectids.values())) or "").strip()
    if not project_id:
        return _fail("missing projectId in ids/config", code=400, data={})
    start_dt, end_dt = _current_quarter_utc_range(expected_mode=expected_mode)
    result = team_quarter_workhours_db_service({
        "projectId": project_id,
        "start_time": start_dt.isoformat(),
        "end_time": end_dt.isoformat(),
        "scopeCode": scope_code,
        "teamCode": team_code,
    })
    if not result.get("success"):
        return _fail(result.get("error", "team quarter aggregate failed"), code=400, data=result.get("data") or {})
    data = result.get("data") or {}
    allowed_ids = list_scope_member_ids(scope_code, team_code)
    data["rows"] = [row for row in data.get("rows", []) if str(row.get("userId") or "").strip() in allowed_ids]
    data["memberOptions"] = [
        {
            "id": str(member.get("id") or member.get("userId") or "").strip(),
            "userId": str(member.get("userId") or member.get("id") or "").strip(),
            "name": str(member.get("name") or member.get("userName") or "").strip(),
            "teamCode": str(member.get("teamCode") or team_code).strip(),
            "teamName": str(member.get("teamName") or "").strip(),
        }
        for member in data.get("memberOptions", [])
        if str(member.get("userId") or member.get("id") or "").strip() in allowed_ids
    ]
    # Keep the public V2 response stable even if an internal/older aggregate
    # implementation accidentally includes its numeric team identifier.
    data.pop("teamId", None)
    data["scopeCode"] = scope_code
    data["teamCode"] = team_code
    return _ok(data)


@dashboard_bp.route("/nav-team-detail", methods=["GET"])
def nav_team_detail():
    """Get the navigation-team quarter detail dashboard."""
    _, denied = require_access(_fail, any_permissions=("page.nav_team_detail",))
    if denied:
        return denied
    expected_mode = str(request.args.get("expected") or "quarter").strip()
    if expected_mode not in {"quarter", "current", "last_quarter"}:
        expected_mode = "quarter"
    return _team_detail_handler(expected_mode, "DEPARTMENT_EFFECTIVE_HOURS", "NAV")


@dashboard_bp.route("/integration-team-detail", methods=["GET"])
def integration_team_detail():
    """Get the integration-team quarter detail dashboard."""
    _, denied = require_access(_fail, any_permissions=("page.integration_team_detail",))
    if denied:
        return denied
    expected_mode = str(request.args.get("expected") or "quarter").strip()
    if expected_mode not in {"quarter", "current", "last_quarter"}:
        expected_mode = "quarter"
    return _team_detail_handler(expected_mode, "DEPARTMENT_EFFECTIVE_HOURS", "INTEGRATION")


@dashboard_bp.route("/application-team-detail", methods=["GET"])
def application_team_detail():
    """Get application team (navigation application-engineer view) quarter detail dashboard."""
    _, denied = require_access(_fail, any_permissions=("page.application_team",))
    if denied:
        return denied
    expected_mode = str(request.args.get("expected") or "quarter").strip()
    if expected_mode not in {"quarter", "current", "last_quarter"}:
        expected_mode = "quarter"
    return _team_detail_handler(expected_mode, "APPLICATION_TEAM_VIEW", "NAV")


@dashboard_bp.route("/app-three-team-detail", methods=["GET"])
def app_three_team_detail():
    """Get the additional formal APP_THREE team dashboard."""
    _, denied = require_access(_fail, any_permissions=("page.app_three_team",))
    if denied:
        return denied
    expected_mode = str(request.args.get("expected") or "quarter").strip()
    if expected_mode not in {"quarter", "current", "last_quarter"}:
        expected_mode = "quarter"
    return _team_detail_handler(expected_mode, "APP_THREE_TEAM_VIEW", "APP_THREE")
