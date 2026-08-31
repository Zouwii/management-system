import unittest
from unittest.mock import patch

from application_team import report_service


class Batch4ScopeTests(unittest.TestCase):
    def test_application_members_are_role_view_not_team_three(self):
        roster = [{
            "userId": "nav-app",
            "userName": "导航应用工程师",
            "teamCode": "NAV",
            "jobRoleCode": "APPLICATION_ENGINEER",
        }]
        with patch.object(report_service, "list_scope_members", return_value=roster) as mocked:
            members = report_service._application_members()
        mocked.assert_called_once_with("APPLICATION_TEAM_VIEW")
        self.assertEqual(members[0]["userId"], "nav-app")
        self.assertEqual(members[0]["teamCode"], "NAV")

    def test_app_three_members_use_formal_team_scope(self):
        roster = [{
            "userId": "app-three",
            "userName": "应用三组成员",
            "teamCode": "APP_THREE",
            "jobRoleCode": "SOFTWARE_ENGINEER",
        }]
        with patch.object(report_service, "list_scope_members", return_value=roster) as mocked:
            members = report_service._application_members("APP_THREE_TEAM_VIEW")
        mocked.assert_called_once_with("APP_THREE_TEAM_VIEW")
        self.assertEqual(members[0]["teamCode"], "APP_THREE")


if __name__ == "__main__":
    unittest.main()
