"""Dashboard team detail routes.

Routes:
  GET /nav-team-detail           - Navigation team quarterly detail
  GET /integration-team-detail   - Integration team quarterly detail
  GET /application-team-detail   - Application team quarterly detail
"""

from flask import request, session

from workhour.personal.aggregate import team_quarter_workhours_db_service, workdays_in_range_service
from base.config.service import get_workhour_character_coefficients_service
from base.dingtalk_client import get_config_projectids

from base.route_registry.dashboard import (
    _current_quarter_utc_range,
    _fail,
    _member_role_label_from_user_character,
    _ok,
    _require_login,
    _to_character,
    dashboard_bp,
)


def _group_detail_rows(team_id_value: str, expected_mode: str = "quarter"):
    """Build aggregated team detail rows from DB for a given team.

    Queries the A/B/C task tables for all team members and computes
    scheduled, completed, and overdue hours against quarterly expectations.

    Args:
        team_id_value: Team ID string ("0"=nav, "1"=servo).
        expected_mode: Quarter mode ("quarter", "current", "last_quarter").

    Returns:
        Dict with rows, quarterRange, and projectId.
    """
    from base.db.engine import SessionLocal
    from base.db.orm import ProjectTask, ProjectTaskDetail, ProjectTaskOverdueDetail, UserCharacter as DbUserCharacter
    from sqlalchemy import and_, func

    projectids = get_config_projectids() or {}
    project_id = ""
    if isinstance(projectids, dict) and projectids:
        project_id = str(next(iter(projectids.values())) or "").strip()

    start_dt, end_dt = _current_quarter_utc_range(expected_mode=expected_mode)
    expected_out = workdays_in_range_service({
        "start_time": start_dt.isoformat(),
        "end_time": end_dt.isoformat(),
        "compensatoryDays": 0,
    })
    quarter_expected_days = float(((expected_out.get("data") or {}).get("effective_workday_count")) or 0.0)
    coeff_out = get_workhour_character_coefficients_service() or {}
    coeff_map = coeff_out.get("workhour_character_coefficients") or {}

    session = SessionLocal()
    try:
        members = (
            session.query(DbUserCharacter)
            .filter(DbUserCharacter.team_id == str(team_id_value))
            .filter(DbUserCharacter.character != 0)
            .order_by(DbUserCharacter.user_id.asc())
            .all()
        )

        rows = []
        for m in members:
            uid = str(getattr(m, "user_id", "") or "").strip()
            if not uid:
                continue
            name = str(getattr(m, "name", "") or uid)
            role_label = _member_role_label_from_user_character(
                getattr(m, "character", 1),
                getattr(m, "is_nav_lead", False),
                getattr(m, "is_servo_lead", False),
            )
            member_character = _to_character(getattr(m, "character", None), default=0)
            if member_character in (0, 9):
                continue
            coefficient = float(coeff_map.get(str(member_character), 1.0) or 1.0)
            expected_effective_hours = quarter_expected_days * coefficient

            b_base = (
                session.query(ProjectTaskDetail)
                .join(
                    ProjectTask,
                    and_(
                        ProjectTask.project_id == ProjectTaskDetail.project_id,
                        ProjectTask.task_id == ProjectTaskDetail.task_id,
                    ),
                )
                .filter(ProjectTaskDetail.query_user_id == uid)
                .filter(ProjectTask.due_date != None)  # noqa: E711
                .filter(ProjectTask.due_date >= start_dt)
                .filter(ProjectTask.due_date <= end_dt)
            )
            if project_id:
                b_base = b_base.filter(ProjectTaskDetail.project_id == project_id)

            scheduled_total = float(
                b_base.with_entities(func.coalesce(func.sum(ProjectTaskDetail.work_hour), 0.0)).scalar() or 0.0
            )
            completed_total = float(
                b_base.filter(ProjectTaskDetail.task_flow_status_id == 4)
                .with_entities(func.coalesce(func.sum(ProjectTaskDetail.work_hour), 0.0))
                .scalar()
                or 0.0
            )

            c_base = (
                session.query(ProjectTaskOverdueDetail)
                .join(
                    ProjectTask,
                    and_(
                        ProjectTask.project_id == ProjectTaskOverdueDetail.project_id,
                        ProjectTask.task_id == ProjectTaskOverdueDetail.task_id,
                    ),
                )
                .filter(ProjectTaskOverdueDetail.query_user_id == uid)
            )
            if project_id:
                c_base = c_base.filter(ProjectTaskOverdueDetail.project_id == project_id)
            overdue_effective_total = float(
                c_base.with_entities(func.coalesce(func.sum(ProjectTaskOverdueDetail.work_hour), 0.0)).scalar() or 0.0
            )
            overdue_completed_total = float(
                c_base.filter(ProjectTaskOverdueDetail.task_flow_status_id == 4)
                .with_entities(func.coalesce(func.sum(ProjectTaskOverdueDetail.work_hour), 0.0))
                .scalar()
                or 0.0
            )

            allocation_delta = scheduled_total + overdue_effective_total - expected_effective_hours
            completion_delta = completed_total + overdue_completed_total - expected_effective_hours

            rows.append({
                "userId": uid,
                "name": name,
                "role": role_label,
                "quarterExpectedHours": round(expected_effective_hours, 2),
                "workdayCount": round(quarter_expected_days, 2),
                "character": member_character,
                "coefficient": coefficient,
                "scheduledHours": round(scheduled_total, 2),
                "completedHours": round(completed_total, 2),
                "overdueEffectiveHours": round(overdue_effective_total, 2),
                "overdueCompletedHours": round(overdue_completed_total, 2),
                "allocationDelta": round(allocation_delta, 2),
                "completionDelta": round(completion_delta, 2),
                "hours": round(scheduled_total, 2),
            })
        return {
            "rows": rows,
            "quarterRange": {"startTime": start_dt.isoformat(), "endTime": end_dt.isoformat()},
            "projectId": project_id,
        }
    finally:
        session.close()


def _team_detail_handler(team_id: str, expected_mode: str):
    """Shared handler for both team detail endpoints.

    Args:
        team_id: "0" for nav team, "1" for integration team, "3" for application team.
        expected_mode: Quarter mode string.
    """
    projectids = get_config_projectids() or {}
    project_id = ""
    if isinstance(projectids, dict) and projectids:
        project_id = str(next(iter(projectids.values())) or "").strip()
    if not project_id:
        return _fail("missing projectId in ids/config", code=400, data={})
    start_dt, end_dt = _current_quarter_utc_range(expected_mode=expected_mode)
    result = team_quarter_workhours_db_service({
        "teamId": team_id,
        "projectId": project_id,
        "start_time": start_dt.isoformat(),
        "end_time": end_dt.isoformat(),
        "exclude_character_zero": True,
    })
    if not result.get("success"):
        return _fail(result.get("error", "team quarter aggregate failed"), code=400, data=result.get("data") or {})
    return _ok(result.get("data") or {})


@dashboard_bp.route("/nav-team-detail", methods=["GET"])
def nav_team_detail():
    """Get navigation team (teamId=0) quarter detail dashboard."""
    user = _require_login()
    if not user:
        return _fail("unauthenticated", code=401, data={})
    expected_mode = str(request.args.get("expected") or "quarter").strip()
    if expected_mode not in {"quarter", "current", "last_quarter"}:
        expected_mode = "quarter"
    return _team_detail_handler("0", expected_mode)


@dashboard_bp.route("/integration-team-detail", methods=["GET"])
def integration_team_detail():
    """Get integration team (teamId=1) quarter detail dashboard."""
    user = _require_login()
    if not user:
        return _fail("unauthenticated", code=401, data={})
    expected_mode = str(request.args.get("expected") or "quarter").strip()
    if expected_mode not in {"quarter", "current", "last_quarter"}:
        expected_mode = "quarter"
    return _team_detail_handler("1", expected_mode)


@dashboard_bp.route("/application-team-detail", methods=["GET"])
def application_team_detail():
    """Get application team (teamId=3) quarter detail dashboard."""
    user = _require_login()
    if not user:
        return _fail("unauthenticated", code=401, data={})
    expected_mode = str(request.args.get("expected") or "quarter").strip()
    if expected_mode not in {"quarter", "current", "last_quarter"}:
        expected_mode = "quarter"
    return _team_detail_handler("3", expected_mode)
