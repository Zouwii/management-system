import unittest
import sys
import types
from datetime import datetime, timezone
from unittest.mock import patch

# Team-detail tests do not exercise calendar calculations.
sys.modules.setdefault("chinese_calendar", types.SimpleNamespace(
    is_workday=lambda _day: True,
    is_holiday=lambda _day: False,
))

from workhour.team import routes
from workhour.personal.aggregate import team_quarter_workhours_db_service


class TeamDetailRoutesV2Tests(unittest.TestCase):
    def test_aggregate_rejects_legacy_team_id_contract(self):
        result = team_quarter_workhours_db_service({"teamId": "0", "projectId": "project-1"})
        self.assertFalse(result["success"])
        self.assertIn("scopeCode and teamCode", result["error"])

    @patch.object(routes, "_ok", side_effect=lambda data: data)
    @patch.object(routes, "list_scope_member_ids", return_value={"u1"})
    @patch.object(routes, "team_quarter_workhours_db_service")
    @patch.object(routes, "_current_quarter_utc_range")
    @patch.object(routes, "get_config_projectids", return_value={"main": "project-1"})
    def test_handler_uses_stable_scope_and_team_codes(
        self,
        _projects,
        quarter_range,
        aggregate,
        scope_member_ids,
        _ok,
    ):
        now = datetime(2026, 7, 1, tzinfo=timezone.utc)
        quarter_range.return_value = (now, now)
        aggregate.return_value = {
            "success": True,
            "data": {
                "teamId": "0",
                "rows": [{"userId": "u1"}, {"userId": "outside"}],
                "memberOptions": [
                    {"id": "u1", "name": "张三", "teamId": "0", "teamCode": "NAV", "teamName": "导航组"},
                    {"id": "outside", "name": "范围外"},
                ],
            },
        }

        result = routes._team_detail_handler("quarter", "DEPARTMENT_EFFECTIVE_HOURS", "NAV")

        payload = aggregate.call_args.args[0]
        self.assertNotIn("teamId", payload)
        self.assertEqual(payload["scopeCode"], "DEPARTMENT_EFFECTIVE_HOURS")
        self.assertEqual(payload["teamCode"], "NAV")
        scope_member_ids.assert_called_once_with("DEPARTMENT_EFFECTIVE_HOURS", "NAV")
        self.assertEqual(result["teamCode"], "NAV")
        self.assertEqual(result["scopeCode"], "DEPARTMENT_EFFECTIVE_HOURS")
        self.assertNotIn("teamId", result)
        self.assertEqual(result["rows"], [{"userId": "u1"}])
        self.assertEqual(result["memberOptions"], [{
            "id": "u1",
            "userId": "u1",
            "name": "张三",
            "teamCode": "NAV",
            "teamName": "导航组",
        }])


if __name__ == "__main__":
    unittest.main()
