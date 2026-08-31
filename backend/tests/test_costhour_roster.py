import unittest
from unittest.mock import patch

from workhour.costhour import attendance
from workhour.costhour import service


class _Query:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *_args, **_kwargs):
        return self

    def all(self):
        return self.rows

    def first(self):
        return self.rows[0] if self.rows else None


class _Session:
    def __init__(self, rows=()):
        self.rows = list(rows)
        self.added = []
        self.committed = False

    def query(self, *_args):
        return _Query(self.rows)

    def add(self, row):
        self.added.append(row)

    def commit(self):
        self.committed = True

    def rollback(self):
        pass

    def close(self):
        pass


class CosthourRosterTests(unittest.TestCase):
    @patch.object(service, "_query_workday_costhour_base", return_value=[{
        "userId": "u1",
        "teamCode": "NAV",
        "teamName": "导航组",
        "workdayCosthour": 2.0,
        "projectType": "研发",
        "taskType": "软件开发",
    }])
    def test_team_summary_contract_uses_team_code(self, _query):
        result = service.workday_costhour_team_summary_service({
            "start_time": "2026-01-01T00:00:00+00:00",
            "end_time": "2026-03-31T23:59:59+00:00",
        })
        self.assertTrue(result["success"])
        team = result["data"]["teams"][0]
        self.assertEqual(team["teamCode"], "NAV")
        self.assertNotIn("teamId", team)

    @patch.object(service, "list_scope_teams", return_value={
        "teams": [{"code": "NAV", "name": "导航组"}],
    })
    @patch.object(service, "list_scope_members", return_value=[{
        "userId": "u1", "userName": "张三", "teamCode": "NAV", "teamName": "导航组",
    }])
    @patch.object(service, "_query_workday_costhour_base", return_value=[])
    def test_member_summary_contract_uses_team_code(self, _query, _members, _teams):
        result = service.workday_costhour_member_summary_service({
            "start_time": "2026-01-01T00:00:00+00:00",
            "end_time": "2026-03-31T23:59:59+00:00",
            "teamCode": "NAV",
        })
        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["teamCode"], "NAV")
        self.assertNotIn("teamId", result["data"])
        self.assertEqual(result["data"]["members"][0]["teamCode"], "NAV")
        self.assertNotIn("teamId", result["data"]["members"][0])

    @patch.object(service, "_query_workday_costhour_base", return_value=[{
        "userId": "u1",
        "userName": "张三",
        "teamCode": "NAV",
        "projectType": "研发项目",
        "taskId": "task-1",
        "content": "任务",
        "taskType": "软件开发",
        "vehicleType2": "车型A",
        "workdayCosthour": 2.0,
    }])
    def test_team_project_detail_requires_and_returns_team_code(self, _query):
        result = service.workday_costhour_team_project_detail_service({
            "start_time": "2026-01-01T00:00:00+00:00",
            "end_time": "2026-03-31T23:59:59+00:00",
            "teamCode": "NAV",
            "project_type": "研发项目",
        })
        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["teamCode"], "NAV")
        self.assertNotIn("teamId", result["data"])

        legacy = service.workday_costhour_team_project_detail_service({
            "start_time": "2026-01-01T00:00:00+00:00",
            "end_time": "2026-03-31T23:59:59+00:00",
            "team_id": "0",
            "project_type": "研发项目",
        })
        self.assertFalse(legacy["success"])

    def test_attendance_get_backfills_members_without_saved_rows(self):
        session = _Session([])
        roster = [{"userId": "u1", "userName": "张三", "teamCode": "ALGORITHM"}]
        with patch.object(attendance, "get_session", return_value=session), patch.object(
            attendance, "list_scope_members", return_value=roster
        ):
            result = attendance.get_attendance_service({"start_time": "2026-01-01T00:00:00"})
        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["records"][0]["teamCode"], "ALGORITHM")
        self.assertNotIn("team_id", result["data"]["records"][0])
        self.assertEqual(result["data"]["records"][0]["overtime_days"], 0)

    def test_attendance_save_does_not_require_client_team_fields(self):
        session = _Session([])
        roster = [{"userId": "u1", "userName": "张三", "teamCode": "NAV"}]
        with patch.object(attendance, "get_session", return_value=session), patch.object(
            attendance, "list_scope_members", return_value=roster
        ):
            result = attendance.save_attendance_service({
                "start_time": "2026-01-01T00:00:00",
                "records": [{"user_id": "u1", "overtime_days": 1}],
            })
        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["saved_count"], 1)
        self.assertEqual(session.added[0].team_code, "NAV")
        self.assertIsNone(session.added[0].team_id)

    def test_attendance_save_ignores_non_roster_ids(self):
        session = _Session([])
        roster = [{"userId": "u1", "userName": "张三", "teamCode": "NAV"}]
        with patch.object(attendance, "get_session", return_value=session), patch.object(
            attendance, "list_scope_members", return_value=roster
        ):
            result = attendance.save_attendance_service({
                "start_time": "2026-01-01T00:00:00",
                "records": [{"user_id": "outside", "overtime_days": 4}],
            })
        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["saved_count"], 0)
        self.assertTrue(session.committed)


if __name__ == "__main__":
    unittest.main()
