import unittest

from base.organization.constants import (
    normalize_role_code,
    normalize_team_code,
    stable_role_code,
    stable_team_code,
)
from base.organization.scopes import get_scope_policy


class ScopePolicyTests(unittest.TestCase):
    def test_legacy_values_normalize_to_stable_codes(self):
        self.assertEqual(normalize_team_code("0"), "NAV")
        self.assertEqual(normalize_team_code(0), "NAV")
        self.assertEqual(normalize_team_code("导航组"), "NAV")
        # Historical numeric 3 is ambiguous and must be resolved by the
        # explicit roster migration, never by runtime normalization.
        self.assertEqual(normalize_team_code("3"), "")
        self.assertEqual(normalize_team_code("APP_THREE"), "APP_THREE")
        self.assertEqual(normalize_role_code(3), "APPLICATION_ENGINEER")
        self.assertEqual(normalize_role_code(0), "TEAM_LEAD")
        self.assertEqual(normalize_role_code("9"), "SYSTEM_ADMIN")

    def test_scope_matrix_matches_first_phase_contract(self):
        self.assertEqual(
            get_scope_policy("department_effective_hours")["teams"],
            ("NAV", "INTEGRATION"),
        )

    def test_runtime_validators_reject_legacy_values(self):
        self.assertEqual(stable_team_code("NAV"), "NAV")
        self.assertEqual(stable_team_code("0"), "")
        self.assertEqual(stable_team_code("导航组"), "")
        self.assertEqual(stable_role_code("APPLICATION_ENGINEER"), "APPLICATION_ENGINEER")
        self.assertEqual(stable_role_code("3"), "")
        self.assertEqual(
            get_scope_policy("WORKDAY_COST")["teams"],
            ("NAV", "INTEGRATION", "ALGORITHM"),
        )
        self.assertEqual(
            get_scope_policy("APPLICATION_TEAM_VIEW"),
            {"teams": ("NAV",), "roles": ("APPLICATION_ENGINEER",)},
        )

    def test_unknown_scope_is_rejected(self):
        with self.assertRaises(ValueError):
            get_scope_policy("not-a-scope")


if __name__ == "__main__":
    unittest.main()
