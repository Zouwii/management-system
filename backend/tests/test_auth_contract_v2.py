import unittest
from unittest.mock import patch

from base.auth.service import _derive_role_and_access, _normalize_profile, resolve_user_profile


class AuthContractV2Tests(unittest.TestCase):
    def test_access_role_is_derived_from_job_role_code(self):
        self.assertEqual(_derive_role_and_access("SOFTWARE_ENGINEER", False, False)["role"], "employee")
        nav_lead = _derive_role_and_access("TEAM_LEAD", True, False)
        self.assertEqual(nav_lead["role"], "manager")
        self.assertEqual(nav_lead["dataScope"], "team")
        self.assertEqual(_derive_role_and_access("SYSTEM_ADMIN", False, False)["role"], "admin")

    def test_app_three_lead_has_dedicated_manager_access(self):
        p3_lead = _derive_role_and_access("TEAM_LEAD", False, False, True)
        self.assertEqual(p3_lead["role"], "manager")
        self.assertEqual(p3_lead["dataScope"], "team")
        self.assertEqual(p3_lead["homePath"], "/manager/app-three-team")
        self.assertIn("page.app_three_team", p3_lead["permissionCodes"])
        self.assertNotIn("page.nav_team_detail", p3_lead["permissionCodes"])
        self.assertNotIn("page.integration_team_detail", p3_lead["permissionCodes"])

    def test_profile_exposes_stable_organization_fields_only(self):
        profile = _normalize_profile({
            "id": "u1",
            "user_id": "u1",
            "name": "张三",
            "role": "employee",
            "teamCode": "NAV",
            "jobRoleCode": "APPLICATION_ENGINEER",
            "character": 3,
            "teamId": "0",
            "team": "导航组",
        }, {"userid": "u1"})

        self.assertEqual(profile["teamCode"], "NAV")
        self.assertEqual(profile["teamName"], "导航组")
        self.assertEqual(profile["jobRoleCode"], "APPLICATION_ENGINEER")
        self.assertEqual(profile["jobRoleName"], "应用工程师")
        self.assertNotIn("teamId", profile)
        self.assertNotIn("team", profile)
        self.assertNotIn("character", profile)
        self.assertNotIn("isNavLead", profile)
        self.assertNotIn("isServoLead", profile)

    @patch("base.auth.service._get_user_character_row", return_value=None)
    def test_unknown_dingtalk_user_is_rejected(self, _row):
        result = resolve_user_profile({"userid": "not-in-roster", "nick": "未知用户"})
        self.assertFalse(result["ok"])
        self.assertIn("organization roster", result["error"])


if __name__ == "__main__":
    unittest.main()
