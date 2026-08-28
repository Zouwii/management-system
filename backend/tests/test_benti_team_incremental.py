from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from base.sync import task_sync


def _list_result(rows):
    return {
        "success": True,
        "data": {"dingtalk": {"result": rows}},
        "meta": {"page_count": 1},
    }


class _FakeSession:
    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


class _ExistingRowSession:
    def __init__(self, row):
        self.row = row

    def scalars(self, _statement):
        return self

    def first(self):
        return self.row


class BentiTeamIncrementalTests(unittest.TestCase):
    def test_issue_detail_writes_software_version_without_name_error(self):
        row = SimpleNamespace()
        session = _ExistingRowSession(row)
        item = {
            "taskId": "issue-1",
            "executorId": "u1",
            "customFields": [
                {
                    "customFieldId": task_sync.PROGRAM_SOFTWARE_VERSION_FIELD_ID,
                    "value": [{"title": "v1.2.3"}],
                }
            ],
        }

        result = task_sync._sync_one_issue_detail(
            session,
            executor_id="u1",
            task_id="issue-1",
            project_id="project-1",
            item=item,
            field_id="work-hour",
            now=datetime.now(timezone.utc),
            business_type_mapping={},
        )

        self.assertIsNone(result["work_hour"])
        self.assertEqual(row.software_version, "v1.2.3")

    def _common_patches(self):
        return (
            patch.object(task_sync, "_acquire_update_lock", return_value={"ok": True}),
            patch.object(task_sync, "_release_update_lock"),
            patch.object(task_sync, "_load_allowed_executor_ids", return_value={"u1", "u2"}),
            patch.object(task_sync, "_safe_last_update_time"),
            patch.object(task_sync, "get_valid_access_token", return_value={"ok": True, "access_token": "token"}),
            patch.object(task_sync, "SessionLocal", return_value=_FakeSession()),
            patch.object(task_sync, "_get_business_type_tag_mapping", return_value={}),
            patch.object(task_sync, "_get_task_flow_status_mapping", return_value={}),
            patch.object(task_sync, "_sync_one_detail_to_b_and_c"),
            patch.object(task_sync, "_sync_one_issue_detail"),
            patch.object(task_sync, "_upsert_config_value"),
        )

    def test_deduplicates_cross_member_tasks_and_excludes_algorithm_executor(self):
        dev = {
            "taskId": "dev-1",
            "executorId": "u1",
            "scenarioFieldConfigId": task_sync.DEFAULT_SCENARIO_FIELD_CONFIG_ID,
        }
        issue = {
            "taskId": "issue-1",
            "executorId": "u2",
            "scenarioFieldConfigId": task_sync.ISSUE_SCENARIO_FIELD_CONFIG_ID,
        }
        algorithm = {
            "taskId": "algo-1",
            "executorId": "algorithm-user",
            "scenarioFieldConfigId": task_sync.DEFAULT_SCENARIO_FIELD_CONFIG_ID,
        }

        patches = self._common_patches()
        with patches[0], patches[1] as release, patches[2], patches[3] as last_time, \
                patches[4], patches[5], patches[6], patches[7], \
                patches[8] as write_dev, patches[9] as write_issue, patches[10] as update_time, \
                patch.object(
                    task_sync,
                    "query_project_tasks_service",
                    side_effect=[_list_result([dev, issue, algorithm]), _list_result([dev, issue])],
                ) as query_lists, patch.object(
                    task_sync,
                    "query_user_tasks_service",
                    side_effect=lambda payload: {
                        "success": True,
                        "data": {"dingtalk": {"result": {"taskId": payload["taskId"]}}},
                    },
                ) as query_details, patch.object(
                    task_sync,
                    "sync_project_tasks_to_db",
                    return_value={"success": True, "data": {"upserted": 2}},
                ) as sync_a:
            from datetime import datetime, timezone
            last_time.return_value = datetime(2026, 8, 1, tzinfo=timezone.utc)
            result = task_sync.benti_team_incremental_update_service({"projectId": "project-1"})

        self.assertTrue(result["success"])
        self.assertEqual(query_lists.call_count, 2)
        self.assertEqual(query_details.call_count, 2)
        self.assertEqual(result["data"]["uniqueTaskCountBeforeExecutorFilter"], 3)
        self.assertEqual(result["data"]["uniqueTaskCount"], 2)
        self.assertEqual(result["data"]["skippedExecutors"], {"dev": 1, "issue": 0})
        self.assertEqual(result["data"]["written"], {"dev": 1, "issue": 1})
        merged_rows = sync_a.call_args.kwargs["query_result"]["data"]["dingtalk"]["result"]
        self.assertEqual({row["taskId"] for row in merged_rows}, {"dev-1", "issue-1"})
        write_dev.assert_called_once()
        write_issue.assert_called_once()
        update_time.assert_called_once()
        release.assert_called_once()

    def test_detail_failure_does_not_write_or_advance_cursor(self):
        dev = {
            "taskId": "dev-1",
            "executorId": "u1",
            "scenarioFieldConfigId": task_sync.DEFAULT_SCENARIO_FIELD_CONFIG_ID,
        }
        patches = self._common_patches()
        with patches[0], patches[1] as release, patches[2], patches[3] as last_time, \
                patches[4], patches[5], patches[6], patches[7], patches[8], patches[9], \
                patches[10] as update_time, patch.object(
                    task_sync, "query_project_tasks_service", side_effect=[_list_result([dev]), _list_result([dev])]
                ), patch.object(
                    task_sync,
                    "query_user_tasks_service",
                    return_value={"success": False, "error": "timeout"},
                ) as query_details, patch.object(
                    task_sync, "sync_project_tasks_to_db"
                ) as sync_a, patch.object(task_sync, "_record_sync_failures"):
            from datetime import datetime, timezone
            last_time.return_value = datetime(2026, 8, 1, tzinfo=timezone.utc)
            result = task_sync.benti_team_incremental_update_service({"projectId": "project-1"})

        self.assertFalse(result["success"])
        self.assertEqual(query_details.call_count, 3)
        sync_a.assert_not_called()
        update_time.assert_not_called()
        release.assert_called_once()

    def test_member_list_failure_returns_dingtalk_context(self):
        failure = {
            "success": False,
            "data": {
                "status_code": 500,
                "dingtalk": {
                    "code": "InternalError",
                    "message": "upstream failed",
                    "requestId": "request-1",
                },
            },
            "meta": {"page_count": 0, "fetched_count": 0},
        }
        patches = self._common_patches()
        with patches[0], patches[1] as release, patches[2], patches[3] as last_time, \
                patches[4], patches[5], patches[6], patches[7], patches[8], patches[9], \
                patches[10] as update_time, patch.object(
                    task_sync, "query_project_tasks_service", return_value=failure
                ) as query_lists:
            last_time.return_value = datetime(2026, 8, 1, tzinfo=timezone.utc)
            result = task_sync.benti_team_incremental_update_service({"projectId": "project-1"})

        self.assertFalse(result["success"])
        self.assertEqual(query_lists.call_count, 3)
        self.assertEqual(result["data"]["failedMember"], "u1")
        self.assertEqual(result["data"]["failedAttempts"], 3)
        self.assertEqual(result["data"]["failure"]["status_code"], 500)
        self.assertEqual(result["data"]["failure"]["code"], "InternalError")
        self.assertEqual(result["data"]["failure"]["request_id"], "request-1")
        update_time.assert_not_called()
        release.assert_called_once()


if __name__ == "__main__":
    unittest.main()
