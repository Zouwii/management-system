import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from base.sync import task_sync


class _EmptyQuery:
    def filter(self, *_args):
        return self

    def order_by(self, *_args):
        return self

    def all(self):
        return []


class _Session:
    def query(self, *_args):
        return _EmptyQuery()

    def close(self):
        pass


class SyncRosterContractTests(unittest.TestCase):
    @patch("base.config.service.touch_last_update_time_service", return_value={"success": True})
    @patch.object(task_sync, "_record_sync_failures")
    @patch.object(task_sync, "_get_task_flow_status_mapping", return_value={})
    @patch.object(task_sync, "_get_business_type_tag_mapping", return_value={})
    @patch.object(task_sync, "_load_allowed_executor_ids", return_value={"u1"})
    @patch.object(task_sync, "SessionLocal", return_value=_Session())
    @patch.object(task_sync, "get_valid_access_token", return_value={"ok": True, "access_token": "token"})
    @patch.object(task_sync, "sync_project_tasks_to_db", return_value={"success": True, "data": {}})
    @patch.object(task_sync, "query_project_tasks_service", return_value={"success": True, "data": {}})
    @patch.object(task_sync, "_safe_last_update_time", return_value=datetime(2026, 1, 1, tzinfo=timezone.utc))
    def test_time_range_sync_returns_roster_filter_contract(self, *_mocks):
        result = task_sync.sync_project_details_in_time_range_service({
            "userId": "u1",
            "projectId": "p1",
            "startDate": "2026-01-01T00:00:00+00:00",
            "endDate": "2026-03-31T23:59:59+00:00",
        })

        self.assertTrue(result["success"])
        b_sync = result["data"]["b_sync"]
        self.assertEqual(b_sync["skipped_outside_roster"], 0)
        self.assertNotIn("skipped_by_character", b_sync)


if __name__ == "__main__":
    unittest.main()
