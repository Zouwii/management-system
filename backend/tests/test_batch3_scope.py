import unittest
import sys
import types
from unittest.mock import patch

# The aggregate module imports this optional calendar package at import time;
# these tests exercise only roster selection and do not need its calculations.
sys.modules.setdefault("chinese_calendar", types.SimpleNamespace(is_workday=lambda _d: True, is_holiday=lambda _d: False))

from base.department import service as department_service
from performance import service as performance_service


class Batch3ScopeTests(unittest.TestCase):
    def test_department_members_use_effective_hours_scope(self):
        roster = [
            {
                "userId": "nav", "userName": "导航", "teamCode": "NAV", "teamName": "导航组",
                "jobRoleCode": "SOFTWARE_ENGINEER", "jobRoleName": "软件开发工程师", "isTeamLead": False,
            },
            {
                "userId": "servo", "userName": "对接", "teamCode": "INTEGRATION", "teamName": "对接组",
                "jobRoleCode": "SOFTWARE_APPLICATION_ENGINEER", "jobRoleName": "软件应用工程师", "isTeamLead": False,
            },
            {
                "userId": "algo", "userName": "算法", "teamCode": "ALGORITHM", "teamName": "算法组",
                "jobRoleCode": "ALGORITHM_ENGINEER", "jobRoleName": "算法工程师", "isTeamLead": False,
            },
        ]
        with patch.object(department_service, "list_scope_members", return_value=roster) as mocked:
            members = department_service._fetch_members()
        mocked.assert_called_once_with("DEPARTMENT_EFFECTIVE_HOURS")
        self.assertEqual({m["userId"] for m in members}, {"nav", "servo"})
        self.assertEqual(members[0]["jobRoleCode"], "SOFTWARE_ENGINEER")
        self.assertNotIn("character", members[0])
        self.assertNotIn("teamKey", members[0])

    def test_performance_team_options_are_scope_driven(self):
        scope_teams = {"teams": [
            {"code": "NAV", "name": "导航组"},
            {"code": "INTEGRATION", "name": "对接组"},
        ]}
        with patch.object(performance_service, "list_scope_teams", return_value=scope_teams) as mocked:
            result = performance_service.list_teams_service()
        mocked.assert_called_once_with("QUARTER_PERFORMANCE")
        self.assertEqual(result["data"]["teams"], [
            {"teamCode": "NAV", "teamName": "导航组"},
            {"teamCode": "INTEGRATION", "teamName": "对接组"},
        ])

    def test_performance_member_filter_uses_scope(self):
        roster = [{
            "userId": "nav", "userName": "导航", "teamCode": "NAV", "teamName": "导航组",
            "jobRoleCode": "SOFTWARE_ENGINEER", "jobRoleName": "软件开发工程师",
        }]
        with patch.object(performance_service, "list_scope_members", return_value=roster) as mocked:
            result = performance_service.list_members_service({"teamCode": "NAV"})
        mocked.assert_called_once_with("QUARTER_PERFORMANCE", "NAV")
        member = result["data"]["members"][0]
        self.assertEqual(member["teamCode"], "NAV")
        self.assertNotIn("teamKey", member)
        self.assertNotIn("character", member)

    def test_performance_import_users_rejects_legacy_team_alias(self):
        result = performance_service.list_team_import_users_service({
            "year": 2026,
            "quarter": 3,
            "team": "nav",
        })
        self.assertFalse(result["success"])
        self.assertIn("teamCode", result["error"])


if __name__ == "__main__":
    unittest.main()
