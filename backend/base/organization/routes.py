"""Organization roster APIs."""

from flask import request

from base.auth.access import require_access
from .service import list_scope_members, list_scope_teams


_SCOPE_PERMISSION = {
    "DEPARTMENT_EFFECTIVE_HOURS": "page.department_overview",
    "WORKDAY_COST": "page.workday_costhour",
    "ATTENDANCE": "page.workday_costhour",
    "QUARTER_PERFORMANCE": "button.review_member",
    "APPLICATION_TEAM_VIEW": "page.application_team",
    "APP_THREE_TEAM_VIEW": "page.app_three_team",
    "TB_TASK_SYNC": "page.department_overview",
}


def _public_team(team):
    return {
        "teamCode": str(team.get("teamCode") or team.get("code") or "").strip(),
        "teamName": str(team.get("teamName") or team.get("name") or "").strip(),
    }


def _public_member(member):
    return {
        "userId": str(member.get("userId") or "").strip(),
        "userName": str(member.get("userName") or member.get("name") or "").strip(),
        "teamCode": str(member.get("teamCode") or "").strip(),
        "teamName": str(member.get("teamName") or "").strip(),
        "jobRoleCode": str(member.get("jobRoleCode") or "").strip(),
        "jobRoleName": str(member.get("jobRoleName") or "").strip(),
    }


def register(bp, ok, fail):
    def require_scope_access(scope_code):
        permission = _SCOPE_PERMISSION.get(str(scope_code or "").strip().upper())
        return require_access(fail, any_permissions=(permission,) if permission else ())

    @bp.route("/organization/scopes/<scope_code>/options", methods=["GET"])
    def organization_scope_options(scope_code):
        _, denied = require_scope_access(scope_code)
        if denied:
            return denied
        try:
            roster = list_scope_teams(scope_code)
            members = list_scope_members(
                scope_code,
                request.args.get("teamCode") or None,
            )
            return ok({
                "scopeCode": str(roster.get("scopeCode") or scope_code).strip().upper(),
                "teams": [_public_team(team) for team in roster.get("teams", [])],
                "members": [_public_member(member) for member in members],
            })
        except ValueError as exc:
            return fail(str(exc), code=400, data={})
        except Exception as exc:
            return fail(str(exc), code=500, data={})

    @bp.route("/organization/scopes/<scope_code>/members", methods=["GET"])
    def organization_scope_members(scope_code):
        _, denied = require_scope_access(scope_code)
        if denied:
            return denied
        try:
            members = list_scope_members(
                scope_code,
                request.args.get("teamCode") or None,
            )
            public_members = [_public_member(member) for member in members]
            return ok({
                "scopeCode": str(scope_code).strip().upper(),
                "members": public_members,
                "count": len(public_members),
            })
        except ValueError as exc:
            return fail(str(exc), code=400, data={})
        except Exception as exc:
            return fail(str(exc), code=500, data={})
