import unittest
from types import SimpleNamespace
from unittest.mock import patch

from base.organization import service
from base.organization import migration
from base.organization.migration import build_migration_plan


class _FakeQuery:
    def __init__(self, rows):
        self.rows = rows

    def order_by(self, *_args):
        return self

    def all(self):
        return self.rows


class _FakeSession:
    def __init__(self, rows):
        self.rows = rows

    def query(self, *_args):
        return _FakeQuery(self.rows)

    def close(self):
        pass


class RosterServiceTests(unittest.TestCase):
    def setUp(self):
        self.rows = [
            SimpleNamespace(
                user_id="nav-app",
                name="导航应用工程师",
                team_id="0",
                team_code="NAV",
                character=3,
                job_role_code="APPLICATION_ENGINEER",
                is_nav_lead=False,
                is_servo_lead=False,
            ),
            SimpleNamespace(
                user_id="nav-dev",
                name="导航开发工程师",
                team_id="0",
                team_code="NAV",
                character=1,
                job_role_code="SOFTWARE_ENGINEER",
                is_nav_lead=False,
                is_servo_lead=False,
            ),
            SimpleNamespace(
                user_id="algo",
                name="算法工程师",
                team_id="2",
                team_code="ALGORITHM",
                character=4,
                job_role_code="ALGORITHM_ENGINEER",
                is_nav_lead=False,
                is_servo_lead=False,
            ),
            SimpleNamespace(
                user_id="admin",
                name="管理员",
                team_id="0",
                team_code="NAV",
                character=9,
                job_role_code="SYSTEM_ADMIN",
                is_nav_lead=True,
                is_servo_lead=True,
            ),
        ]

    def test_application_view_is_nav_application_engineers_only(self):
        with patch.object(service, "SessionLocal", return_value=_FakeSession(self.rows)):
            members = service.list_scope_members("APPLICATION_TEAM_VIEW")
        self.assertEqual([m["userId"] for m in members], ["nav-app"])
        self.assertEqual(members[0]["teamCode"], "NAV")
        self.assertEqual(members[0]["jobRoleCode"], "APPLICATION_ENGINEER")

    def test_workday_scope_includes_algorithm_but_not_admin(self):
        with patch.object(service, "SessionLocal", return_value=_FakeSession(self.rows)):
            members = service.list_scope_members("WORKDAY_COST")
        self.assertEqual({m["userId"] for m in members}, {"nav-app", "nav-dev", "algo"})

    def test_scope_teams_are_configured_even_when_empty(self):
        result = service.list_scope_teams("ATTENDANCE")
        self.assertEqual(
            [team["code"] for team in result["teams"]],
            ["NAV", "INTEGRATION", "ALGORITHM"],
        )
        self.assertTrue(all("teamId" not in team for team in result["teams"]))

    def test_team_filter_requires_stable_code(self):
        with patch.object(service, "SessionLocal", return_value=_FakeSession(self.rows)):
            members = service.list_scope_members("WORKDAY_COST", team_code="NAV")
        self.assertEqual({m["userId"] for m in members}, {"nav-app", "nav-dev"})
        with patch.object(service, "SessionLocal", return_value=_FakeSession(self.rows)):
            with self.assertRaises(ValueError):
                service.list_scope_members("WORKDAY_COST", team_code="导航组")

    def test_migration_plan_only_fills_blank_codes(self):
        existing = [SimpleNamespace(user_id="u1", team_code=None, job_role_code=None)]
        source = {"张三": {"userId": "u1", "team_id": 0, "character": 3}}
        plan = build_migration_plan(source, existing)
        self.assertEqual(plan, [{"action": "update", "user_id": "u1", "changes": {
            "team_code": "NAV", "job_role_code": "APPLICATION_ENGINEER"
        }}])

    def test_migration_plan_inserts_new_member(self):
        plan = build_migration_plan(
            {"李四": {
                "userId": "u2",
                "team_id": 2,
                "character": 4,
                "is_p3_lead": True,
            }},
            [],
        )
        self.assertEqual(plan[0]["action"], "insert")
        self.assertEqual(plan[0]["team_code"], "ALGORITHM")
        self.assertEqual(plan[0]["job_role_code"], "ALGORITHM_ENGINEER")
        self.assertTrue(plan[0]["is_p3_lead"])

    def test_migration_resolves_old_team_three_as_application_view(self):
        existing = [SimpleNamespace(
            user_id="old-app",
            team_id="3",
            team_code=None,
            character=1,
            job_role_code="SOFTWARE_ENGINEER",
        )]
        plan = build_migration_plan(
            {"旧应用成员": {"userId": "old-app", "team_id": 3, "character": 1}},
            existing,
        )
        self.assertEqual(plan, [{
            "action": "update",
            "user_id": "old-app",
            "changes": {"team_code": "NAV", "job_role_code": "APPLICATION_ENGINEER"},
        }])

    def test_app_three_requires_explicit_stable_team_code(self):
        plan = build_migration_plan(
            {"应用三组成员": {
                "userId": "app-three",
                "team_id": 3,
                "team_code": "APP_THREE",
                "character": 1,
            }},
            [],
        )
        self.assertEqual(plan[0]["team_code"], "APP_THREE")
        self.assertEqual(plan[0]["job_role_code"], "SOFTWARE_ENGINEER")

    def test_database_only_legacy_member_is_reconciled(self):
        existing = [SimpleNamespace(
            user_id="db-only",
            team_id="0",
            team_code=None,
            character=1,
            job_role_code=None,
        )]
        plan = build_migration_plan({}, existing)
        self.assertEqual(plan, [{
            "action": "update",
            "user_id": "db-only",
            "changes": {"team_code": "NAV", "job_role_code": "SOFTWARE_ENGINEER"},
        }])

    def test_migration_cli_defaults_to_dry_run(self):
        report = {
            "counts": {"insert": 0, "update": 0, "unchanged": 0},
            "databaseOnly": [],
            "actions": [],
            "reconciled": True,
        }
        with patch.object(migration, "migrate_from_ids", return_value=report) as mocked:
            self.assertEqual(migration.main([]), 0)
        mocked.assert_called_once_with(dry_run=True)

    def test_migration_cli_requires_apply_for_writes(self):
        report = {
            "counts": {"insert": 0, "update": 0, "unchanged": 0},
            "databaseOnly": [],
            "actions": [],
            "reconciled": True,
        }
        with patch.object(migration, "migrate_from_ids", return_value=report) as mocked:
            self.assertEqual(migration.main(["--apply"]), 0)
        mocked.assert_called_once_with(dry_run=False)


if __name__ == "__main__":
    unittest.main()
