import unittest
from unittest.mock import patch

from base.sync import task_sync
from base.config import service as config_service
from base.organization import service as organization_service


class Batch5ScopeTests(unittest.TestCase):
    def test_tb_sync_uses_centralized_scope(self):
        with patch.object(task_sync, "list_scope_member_ids", return_value={"nav", "integration"}) as mocked:
            result = task_sync._load_allowed_executor_ids()

        mocked.assert_called_once_with("TB_TASK_SYNC")
        self.assertEqual(result, {"nav", "integration"})

    def test_runtime_user_list_comes_from_database_roster(self):
        roster = [{"userId": "db-user", "userName": "数据库成员"}]
        with patch.object(config_service, "list_all_members", return_value=roster) as mocked:
            result = config_service.get_userids_service()
        mocked.assert_called_once_with()
        self.assertEqual(result["users"], [{"name": "数据库成员", "userId": "db-user"}])

    def test_database_deletion_is_not_rehydrated_from_ids_file(self):
        with patch.object(config_service, "list_all_members", return_value=[]):
            result = config_service.get_userids_service()
        self.assertEqual(result["users"], [])

    def test_sync_operator_is_selected_from_database_roles(self):
        rows = [
            type("Row", (), {
                "user_id": "employee", "name": "员工", "team_id": "0", "team_code": "NAV",
                "character": 1, "job_role_code": "SOFTWARE_ENGINEER",
                "is_nav_lead": False, "is_servo_lead": False,
            })(),
            type("Row", (), {
                "user_id": "lead", "name": "组长", "team_id": "0", "team_code": "NAV",
                "character": 0, "job_role_code": "TEAM_LEAD",
                "is_nav_lead": True, "is_servo_lead": False,
            })(),
        ]
        fake_session = type("Session", (), {
            "query": lambda self, *_args: type("Query", (), {
                "order_by": lambda self, *_args: self,
                "all": lambda self: rows,
            })(),
            "close": lambda self: None,
        })
        self.assertEqual(
            organization_service.resolve_sync_operator_id(session_factory=fake_session),
            "lead",
        )


if __name__ == "__main__":
    unittest.main()
