import unittest
import importlib
from datetime import datetime, timezone
from unittest.mock import patch

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from base.algo.sync import (
    ALGO_MEMBER_IDS,
    ALGO_PROJECTS,
    ALGO_ISSUE_CASCADING_PROJECT_FIELD_ID,
    ALGO_ISSUE_NEED_STATISTIC_FIELD_ID,
    ALGO_ISSUE_WORKDAY_COSTHOUR_FIELD_ID,
    GROUPMAP_CASCADING_PROJECT_FIELD_ID,
    GROUPMAP_NEED_STATISTIC_FIELD_ID,
    GROUPMAP_WORKDAY_COSTHOUR_FIELD_ID,
    GROUPMAP_WORK_HOUR_FIELD_ID,
    _apply_dev_detail,
    _apply_issue_detail,
    _sync_project,
)
from base.db.orm import (
    AlgoIssue,
    AlgoIssueDetail,
    AlgoTask,
    AlgoTaskDetail,
    ProgramIssue,
    ProgramIssueDetail,
    ProjectTask,
    ProjectTaskDetail,
    ProjectTaskOverdueDetail,
    ReqPoolDetail,
    UserCharacter,
)
from base.sync.task_sync import (
    CASCADING_PROJECT_FIELD_ID,
    NEED_STATISTIC_CUSTOMFIELD_ID,
    WORKDAY_DURATION_CUSTOMFIELD_ID,
)


class AlgoOrmParityTest(unittest.TestCase):
    def test_algo_tables_match_benti_tables(self):
        pairs = (
            (ProjectTask, AlgoTask),
            (ProjectTaskDetail, AlgoTaskDetail),
            (ProgramIssue, AlgoIssue),
            (ProgramIssueDetail, AlgoIssueDetail),
        )
        for source, target in pairs:
            self.assertEqual(
                list(source.__table__.columns.keys()),
                list(target.__table__.columns.keys()),
            )

    def test_req_pool_fields_are_preserved(self):
        for field in (
            "custom_fields_json",
            "raw_json",
            "comments_json",
            "attachments_json",
            "fetched_at",
        ):
            self.assertIn(field, ReqPoolDetail.__table__.columns)

    def test_legacy_algo_schema_is_upgraded(self):
        engine_module = importlib.import_module("base.db.engine")

        legacy_engine = create_engine("sqlite:///:memory:")
        with legacy_engine.begin() as conn:
            conn.execute(text("CREATE TABLE algo_tasks (id INTEGER, task_list_id VARCHAR(64), task_stage_id VARCHAR(64))"))
            conn.execute(text("CREATE TABLE algo_task_details (id INTEGER, executor_id VARCHAR(64), taskflow_status_id VARCHAR(64), progress INTEGER)"))
            conn.execute(text("CREATE TABLE algo_issues (id INTEGER, task_list_id VARCHAR(64), task_stage_id VARCHAR(64))"))
            conn.execute(text("CREATE TABLE algo_issue_details (id INTEGER, due_date DATETIME, progress INTEGER, note TEXT)"))
        with patch.object(engine_module, "algo_engine", legacy_engine):
            engine_module._ensure_algo_schema_compatible()

        inspector = inspect(legacy_engine)
        self.assertNotIn("task_list_id", {c["name"] for c in inspector.get_columns("algo_tasks")})
        task_detail_columns = {c["name"] for c in inspector.get_columns("algo_task_details")}
        self.assertIn("parent_task_id", task_detail_columns)
        self.assertIn("is_overdue", task_detail_columns)
        self.assertNotIn("executor_id", task_detail_columns)
        issue_columns = {c["name"] for c in inspector.get_columns("algo_issues")}
        self.assertIn("accomplished_at", issue_columns)
        issue_detail_columns = {c["name"] for c in inspector.get_columns("algo_issue_details")}
        self.assertNotIn("due_date", issue_detail_columns)
        legacy_engine.dispose()


class AlgoSyncMappingTest(unittest.TestCase):
    def test_algorithm_issue_detail_uses_issue_custom_field_ids(self):
        row = AlgoIssueDetail(
            project_id="636f31a87ef5737c3e837d00",
            task_id="6a3e332c2ff11cdce135d080",
            query_user_id="2464543025951000",
            scenario_field_config_id="636f31a8708ae400405aaaab",
            fetched_at=datetime.now(timezone.utc),
        )
        item = {
            "taskId": "6a3e332c2ff11cdce135d080",
            "projectId": "636f31a87ef5737c3e837d00",
            "content": "立体导航2期补充文档：pp标注+costmap预测避障",
            "executorId": "2464543025951000",
            "scenarioFieldConfigId": "636f31a8708ae400405aaaab",
            "customFields": [
                {
                    "customFieldId": ALGO_ISSUE_NEED_STATISTIC_FIELD_ID,
                    "value": [{"title": "是"}],
                },
                {
                    "customFieldId": ALGO_ISSUE_WORKDAY_COSTHOUR_FIELD_ID,
                    "value": [{"title": "1"}],
                },
                {
                    "customFieldId": ALGO_ISSUE_CASCADING_PROJECT_FIELD_ID,
                    "value": [{"title": "产品项目 / 叉车 / 立体导航"}],
                },
            ],
        }

        _apply_issue_detail(
            row,
            project_id=item["projectId"],
            query_user_id="2464543025951000",
            task_id=item["taskId"],
            item=item,
            now=datetime.now(timezone.utc),
            field_id="benti-work-hour",
            business_mapping={},
        )

        self.assertEqual(row.need_statistic, "是")
        self.assertEqual(row.workday_costhour, 1.0)
        self.assertIsNone(row.work_hour)
        self.assertEqual(row.project_category_1, "产品项目")
        self.assertEqual(row.vehicle_type_2, "叉车")
        self.assertEqual(row.project_name_3, "立体导航")

    def test_groupmap_detail_uses_algorithm_custom_field_ids(self):
        row = AlgoTaskDetail(
            project_id="636f343d3997deea0514c030",
            task_id="677f4cb1fc2dd8045ee40042",
            query_user_id="22665556381168535",
        )
        item = {
            "taskId": "677f4cb1fc2dd8045ee40042",
            "projectId": "636f343d3997deea0514c030",
            "content": "禾赛激光定位适配（3588）",
            "customFields": [
                {
                    "customFieldId": GROUPMAP_NEED_STATISTIC_FIELD_ID,
                    "value": [{"title": "是"}],
                },
                {
                    "customFieldId": GROUPMAP_WORK_HOUR_FIELD_ID,
                    "value": [{"title": "3"}],
                },
                {
                    "customFieldId": GROUPMAP_WORKDAY_COSTHOUR_FIELD_ID,
                    "value": [{"title": "4"}],
                },
                {
                    "customFieldId": GROUPMAP_CASCADING_PROJECT_FIELD_ID,
                    "value": [{"title": "产品项目 / 叉车 / 3D激光导航"}],
                },
            ],
        }

        _apply_dev_detail(
            row,
            project_id=item["projectId"],
            query_user_id="22665556381168535",
            task_id=item["taskId"],
            item=item,
            now=datetime.now(timezone.utc),
            field_id="benti-work-hour",
            business_mapping={},
            status_mapping={},
        )

        self.assertEqual(row.work_hour_field_id, GROUPMAP_WORK_HOUR_FIELD_ID)
        self.assertEqual(row.work_hour, 3.0)
        self.assertEqual(row.workday_costhour, 4.0)
        self.assertEqual(row.need_statistic, "是")
        self.assertEqual(row.project_category_1, "产品项目")
        self.assertEqual(row.vehicle_type_2, "叉车")
        self.assertEqual(row.project_name_3, "3D激光导航")

    def test_dev_detail_uses_benti_custom_field_parsers(self):
        row = AlgoTaskDetail(
            project_id="p",
            task_id="t",
            query_user_id="algorithm-member",
        )
        item = {
            "taskId": "t",
            "projectId": "p",
            "content": "算法任务",
            "dueDate": "2026-07-31T10:00:00.000Z",
            "scenarioFieldConfigId": "scenario",
            "taskflowStatusId": "status",
            "customFields": [
                {
                    "customFieldId": NEED_STATISTIC_CUSTOMFIELD_ID,
                    "value": [{"title": "是"}],
                },
                {
                    "customFieldId": WORKDAY_DURATION_CUSTOMFIELD_ID,
                    "value": [{"value": "2.5"}],
                },
                {
                    "customFieldId": CASCADING_PROJECT_FIELD_ID,
                    "value": [{"title": "研发项目 / 通用 / 算法平台"}],
                },
            ],
        }
        _apply_dev_detail(
            row,
            project_id="p",
            query_user_id="algorithm-member",
            task_id="t",
            item=item,
            now=datetime.now(timezone.utc),
            field_id="work-hour",
            business_mapping={},
            status_mapping={"status": 4},
        )
        self.assertEqual(row.query_user_id, "algorithm-member")
        self.assertEqual(row.need_statistic, "是")
        self.assertEqual(row.workday_costhour, 2.5)
        self.assertEqual(row.project_category_1, "研发项目")
        self.assertEqual(row.vehicle_type_2, "通用")
        self.assertEqual(row.project_name_3, "算法平台")
        self.assertEqual(row.task_flow_status_id, 4)

    @patch("base.algo.sync._upsert_detail_rows")
    @patch("base.algo.sync._fetch_detail")
    @patch("base.algo.sync._upsert_a_rows")
    @patch("base.algo.sync._fetch_project_member_tasks")
    def test_a_deduplicates_b_uses_algorithm_executor_once(
        self,
        fetch_list,
        upsert_a,
        fetch_detail,
        upsert_b,
    ):
        task = {
            "taskId": "same-task",
            "projectId": ALGO_PROJECTS[0]["project_id"],
            "scenariofieldconfigId": ALGO_PROJECTS[0]["scenario_field_config_id"],
            "executorId": ALGO_MEMBER_IDS[2],
        }
        fetch_list.side_effect = lambda _token, user_id, _project: {
            "success": True,
            "user_id": user_id,
            "tasks": [task],
            "meta": {"page_count": 1},
        }
        upsert_a.side_effect = lambda _project, tasks, _now, reconcile=False: len(tasks)
        fetch_detail.side_effect = lambda _token, _project, user_id, task_id: {
            "success": True,
            "query_user_id": user_id,
            "task_id": task_id,
            "item": {"taskId": task_id},
            "error": "",
        }
        upsert_b.side_effect = lambda _project, rows, _now, reconcile=False: len(rows)

        result = _sync_project("token", ALGO_PROJECTS[0], thread_count=2)

        self.assertEqual(result["aUpserted"], 1)
        self.assertEqual(result["bUpserted"], 1)
        queried_users = {call.args[2] for call in fetch_detail.call_args_list}
        self.assertEqual(queried_users, {ALGO_MEMBER_IDS[2]})


class AlgoCosthourScopeTest(unittest.TestCase):
    def test_only_statistical_positive_rows_enter_costhour(self):
        from workhour.costhour import service

        main_engine = create_engine("sqlite:///:memory:")
        algo_engine = create_engine("sqlite:///:memory:")
        main_tables = [
            ProjectTask.__table__,
            ProjectTaskDetail.__table__,
            ProjectTaskOverdueDetail.__table__,
            ProgramIssue.__table__,
            ProgramIssueDetail.__table__,
            UserCharacter.__table__,
        ]
        algo_tables = [
            AlgoTask.__table__,
            AlgoTaskDetail.__table__,
            AlgoIssue.__table__,
            AlgoIssueDetail.__table__,
        ]
        for table in main_tables:
            table.create(main_engine, checkfirst=True)
        for table in algo_tables:
            table.create(algo_engine, checkfirst=True)
        main_factory = sessionmaker(bind=main_engine)
        algo_factory = sessionmaker(bind=algo_engine)
        main_session = main_factory()
        algo_session = algo_factory()
        due = datetime(2026, 7, 15, tzinfo=timezone.utc)
        user_id = ALGO_MEMBER_IDS[0]
        main_session.add(
            UserCharacter(
                user_id=user_id,
                name="刘丰",
                character=4,
                team_id="2",
            )
        )
        for task_id, need_statistic, hours in (
            ("included", "是", 2.5),
            ("not-marked", None, 9.0),
            ("zero", "是", 0.0),
        ):
            algo_session.add(
                AlgoTask(
                    project_id=ALGO_PROJECTS[0]["project_id"],
                    task_id=task_id,
                    due_date=due,
                )
            )
            algo_session.add(
                AlgoTaskDetail(
                    project_id=ALGO_PROJECTS[0]["project_id"],
                    task_id=task_id,
                    query_user_id=user_id,
                    need_statistic=need_statistic,
                    workday_costhour=hours,
                    content=task_id,
                )
            )
        main_session.commit()
        main_session.close()
        algo_session.commit()
        algo_session.close()

        with patch.object(service, "SessionLocal", main_factory), patch.object(
            service, "AlgoSessionLocal", algo_factory
        ):
            rows = service._query_workday_costhour_base(
                datetime(2026, 7, 1, tzinfo=timezone.utc),
                datetime(2026, 7, 31, 23, 59, tzinfo=timezone.utc),
            )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["taskId"], "included")
        self.assertEqual(rows[0]["teamId"], "2")
        self.assertEqual(rows[0]["teamName"], "算法组")
        self.assertEqual(rows[0]["taskType"], "软件开发")
        main_engine.dispose()
        algo_engine.dispose()


if __name__ == "__main__":
    unittest.main()
