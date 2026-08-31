from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session

from base.db.config import ALGO_DATABASE_URI, DATABASE_URI, KB_DATABASE_URI, PERF_DATABASE_URI, ONSITE_DATABASE_URI, REQ_POOL_DATABASE_URI, PGVECTOR_DATABASE_URI
from base.db.orm import Base  # 导入即注册 ProjectTask 等到 Base.metadata

# SQLite 下多线程需 check_same_thread=False（Flask 每请求一线程）
_main_connect_args = {}
if DATABASE_URI.startswith("sqlite"):
    _main_connect_args["check_same_thread"] = False

_perf_connect_args = {}
if PERF_DATABASE_URI.startswith("sqlite"):
    _perf_connect_args["check_same_thread"] = False

_kb_connect_args = {}
if KB_DATABASE_URI.startswith("sqlite"):
    _kb_connect_args["check_same_thread"] = False

# 主业务库（任务/配置等）
engine = create_engine(
    DATABASE_URI,
    connect_args=_main_connect_args,
    future=True,
    pool_pre_ping=True,
)

SessionLocal = scoped_session(sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True))

# 绩效专用库（nav/servo 绩效表）
perf_engine = create_engine(
    PERF_DATABASE_URI,
    connect_args=_perf_connect_args,
    future=True,
    pool_pre_ping=True,
)

PerfSessionLocal = scoped_session(sessionmaker(bind=perf_engine, autoflush=False, autocommit=False, future=True))

# 知识库专用引擎（kb_documents / kb_chunks）
kb_engine = create_engine(
    KB_DATABASE_URI,
    connect_args=_kb_connect_args,
    future=True,
    pool_pre_ping=True,
)

KbSessionLocal = scoped_session(sessionmaker(bind=kb_engine, autoflush=False, autocommit=False, future=True))

# onsite_problem 专用库
_onsite_connect_args = {}
if ONSITE_DATABASE_URI.startswith("sqlite"):
    _onsite_connect_args["check_same_thread"] = False

onsite_engine = create_engine(
    ONSITE_DATABASE_URI,
    connect_args=_onsite_connect_args,
    future=True,
    pool_pre_ping=True,
)

OnsiteSessionLocal = scoped_session(sessionmaker(bind=onsite_engine, autoflush=False, autocommit=False, future=True))

# req_pool 专用库
_req_pool_connect_args = {}
if REQ_POOL_DATABASE_URI.startswith("sqlite"):
    _req_pool_connect_args["check_same_thread"] = False

req_pool_engine = create_engine(
    REQ_POOL_DATABASE_URI,
    connect_args=_req_pool_connect_args,
    future=True,
    pool_pre_ping=True,
)

ReqPoolSessionLocal = scoped_session(sessionmaker(bind=req_pool_engine, autoflush=False, autocommit=False, future=True))

# 算法组四张 A/B 表专用库
_algo_connect_args = {}
if ALGO_DATABASE_URI.startswith("sqlite"):
    _algo_connect_args["check_same_thread"] = False

algo_engine = create_engine(
    ALGO_DATABASE_URI,
    connect_args=_algo_connect_args,
    future=True,
    pool_pre_ping=True,
)

AlgoSessionLocal = scoped_session(sessionmaker(bind=algo_engine, autoflush=False, autocommit=False, future=True))

# pgvector（PostgreSQL）embedding 专用引擎
pgvector_engine = create_engine(
    PGVECTOR_DATABASE_URI,
    future=True,
    pool_pre_ping=True,
)

PgVectorSessionLocal = scoped_session(sessionmaker(bind=pgvector_engine, autoflush=False, autocommit=False, future=True))


def _table_registry():
    """
    表注册清单（可视化管理，类似 Go 的 createSQLs/dropSQLs 列表）。
    返回六个列表：(main_tables, perf_tables, kb_tables, onsite_tables, req_pool_tables, algo_tables)
    """
    # 延迟导入以避免循环
    from base.db.orm import (
        AlgoIssue,
        AlgoIssueDetail,
        AlgoTask,
        AlgoTaskDetail,
        ApiCallLog,
        Config as DbConfig,
        MemberAttendance,
        NavPerfQuarterResult,
        OnsiteProblemDetail,
        OnsiteProblemTask,
        ProgramIssue,
        ProgramIssueDetail,
        ProjectTask,
        ProjectTaskDetail,
        ProjectTaskOverdueDetail,
        ReqPoolDetail,
        ReqPoolTask,
        ServoPerfQuarterResult,
        SyncFailure,
        SyncRun,
        UpdateLock,
        UserCharacter as DbUserCharacter,
    )
    from ai.knowledge.models import KbNode, KbDocument, KbChunk

    main_tables = [
        ("api_call_logs", ApiCallLog.__table__),
        ("project_tasks", ProjectTask.__table__),
        ("program_issue", ProgramIssue.__table__),
        ("project_task_details", ProjectTaskDetail.__table__),
        ("program_issue_detail", ProgramIssueDetail.__table__),
        ("project_task_overdue_details", ProjectTaskOverdueDetail.__table__),
        ("sync_runs", SyncRun.__table__),
        ("sync_failures", SyncFailure.__table__),
        ("config", DbConfig.__table__),
        ("update_locks", UpdateLock.__table__),
        ("user_character", DbUserCharacter.__table__),
        ("member_attendance", MemberAttendance.__table__),
    ]
    perf_tables = [
        ("nav_perf_quarter_result", NavPerfQuarterResult.__table__),
        ("servo_perf_quarter_result", ServoPerfQuarterResult.__table__),
    ]
    kb_tables = [
        ("kb_nodes", KbNode.__table__),
        ("kb_documents", KbDocument.__table__),
        ("kb_chunks", KbChunk.__table__),
    ]
    onsite_tables = [
        ("onsite_problem_tasks", OnsiteProblemTask.__table__),
        ("onsite_problem_details", OnsiteProblemDetail.__table__),
    ]
    req_pool_tables = [
        ("req_pool_tasks", ReqPoolTask.__table__),
        ("req_pool_details", ReqPoolDetail.__table__),
    ]
    algo_tables = [
        ("algo_tasks", AlgoTask.__table__),
        ("algo_task_details", AlgoTaskDetail.__table__),
        ("algo_issues", AlgoIssue.__table__),
        ("algo_issue_details", AlgoIssueDetail.__table__),
    ]
    return main_tables, perf_tables, kb_tables, onsite_tables, req_pool_tables, algo_tables


def _execute_table_ops(bind, table_entries, action: str) -> None:
    """
    action:
    - create: CREATE TABLE IF NOT EXISTS ...
    - drop:   DROP TABLE IF EXISTS ...
    """
    if action not in {"create", "drop"}:
        raise ValueError(f"unsupported action: {action}")

    for name, table in table_entries:
        if action == "create":
            print(f"[init_db] create table if not exists: {name}")
            table.create(bind=bind, checkfirst=True)
        else:
            raise ValueError("drop is disabled in this project init flow")


def _ensure_algo_schema_compatible() -> None:
    """将早期算法表升级为与本体 A/B 表一致的字段结构。"""
    from sqlalchemy import inspect, text

    migrations = {
        "algo_tasks": {
            "add": {},
            "drop": ("task_list_id", "task_stage_id"),
        },
        "algo_task_details": {
            "add": {
                "requirement_desc": "TEXT NULL",
                "task_outputs": "TEXT NULL",
                "parent_task_id": "VARCHAR(64) NULL",
                "is_overdue": "BOOLEAN NOT NULL DEFAULT 0",
                "task_flow_status_id": "INTEGER NULL",
            },
            "drop": (
                "executor_id",
                "creator_id",
                "taskflow_status_id",
                "is_done",
                "is_archived",
                "priority",
                "progress",
                "note",
                "visible",
                "created_at_ding",
                "updated_at_ding",
                "ancestor_ids",
                "involve_members",
                "tag_ids",
            ),
        },
        "algo_issues": {
            "add": {"accomplished_at": "DATETIME NULL"},
            "drop": ("task_list_id", "task_stage_id"),
        },
        "algo_issue_details": {
            "add": {},
            "drop": ("due_date", "progress", "note"),
        },
    }

    inspector = inspect(algo_engine)
    for table_name, spec in migrations.items():
        columns = {str(col.get("name") or "") for col in inspector.get_columns(table_name)}
        statements = []
        for column_name, ddl in spec["add"].items():
            if column_name not in columns:
                statements.append(
                    f"ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl}"
                )
        for column_name in spec["drop"]:
            if column_name in columns:
                statements.append(f"ALTER TABLE {table_name} DROP COLUMN {column_name}")
        if not statements:
            continue
        with algo_engine.begin() as conn:
            for statement in statements:
                print(f"[init_db] migrate algo schema: {statement}")
                conn.execute(text(statement))


def init_database() -> None:
    """
    数据库初始化入口（仅 init，不做 drop）：
    - create tables if not exists（主库 + 绩效库）
    - seed 默认配置（不自动导入人员；人员由 organization.migration 显式导入）

    设计目标：初始化内容“可视化、可读、可维护”。
    """
    main_tables, perf_tables, kb_tables, onsite_tables, req_pool_tables, algo_tables = _table_registry()
    # seed 阶段会直接使用这两个 ORM 模型
    from base.db.orm import Config as DbConfig, OnsiteProblemDetail

    print("[init_db] creating tables (no drop) ...")
    _execute_table_ops(engine, main_tables, "create")
    _execute_table_ops(perf_engine, perf_tables, "create")
    _execute_table_ops(kb_engine, kb_tables, "create")
    _execute_table_ops(onsite_engine, onsite_tables, "create")
    # 现场问题 B 表字段迁移；兼容已存在的历史表。
    #
    # OnsiteProblemDetail 的字段是逐步增加的，单纯 create(checkfirst=True)
    # 不会更新已经存在的 onsite_problem_details。历史库如果缺少这些拆列，
    # B 表同步在 INSERT/UPDATE 时会直接失败。因此这里只对可空字段做增量
    # ADD COLUMN，保留旧数据，不改变既有列和约束。
    try:
        from sqlalchemy import inspect, text
        onsite_table = OnsiteProblemDetail.__table__
        onsite_columns = {
            c.get("name") for c in inspect(onsite_engine).get_columns("onsite_problem_details")
        }
        with onsite_engine.begin() as conn:
            for column in onsite_table.columns:
                if column.name in onsite_columns or not column.nullable:
                    continue
                column_type = column.type.compile(dialect=onsite_engine.dialect)
                conn.execute(
                    text(
                        "ALTER TABLE onsite_problem_details "
                        f"ADD COLUMN {column.name} {column_type}"
                    )
                )
                print(f"[init_db] migrate onsite schema: add {column.name} {column_type}")
    except Exception as exc:
        print(f"[init_db] onsite schema migration skipped: {exc}")
    try:
        _execute_table_ops(req_pool_engine, req_pool_tables, "create")
    except Exception as e:
        print(f"[init_db] skip req_pool tables: {e}")
    try:
        _execute_table_ops(algo_engine, algo_tables, "create")
        _ensure_algo_schema_compatible()
    except Exception as e:
        print(f"[init_db] skip algo tables: {e}")

    # 兼容无迁移环境：尝试为 B/C 表补齐新字段/新表（SQLite 场景常见）
    try:
        from sqlalchemy import inspect, text

        inspector = inspect(engine)
        dialect_name = engine.dialect.name

        def _ensure_workday_costhour_float(table_name: str) -> None:
            with engine.begin() as conn:
                try:
                    if dialect_name.startswith("mysql"):
                        conn.execute(
                            text(
                                f"ALTER TABLE {table_name} MODIFY COLUMN workday_costhour FLOAT"
                            )
                        )
                    elif dialect_name.startswith("postgresql"):
                        conn.execute(
                            text(
                                f"ALTER TABLE {table_name} ALTER COLUMN workday_costhour TYPE DOUBLE PRECISION"
                            )
                        )
                    elif dialect_name.startswith("sqlite"):
                        # SQLite 动态类型，历史整型值可直接按浮点读写，无需强制改列类型。
                        pass
                except Exception:
                    # 不阻断启动，保持历史数据库可兼容启动。
                    pass
        cols_b = [c.get("name") for c in inspector.get_columns("project_task_details")]
        if "is_overdue" not in cols_b:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE project_task_details ADD COLUMN is_overdue BOOLEAN NOT NULL DEFAULT 0"
                    )
                )
        if "business_type" not in cols_b:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE project_task_details ADD COLUMN business_type INTEGER"
                    )
                )
        if "task_flow_status_id" not in cols_b:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE project_task_details ADD COLUMN task_flow_status_id INTEGER"
                    )
                )
        if "parent_task_id" not in cols_b:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE project_task_details ADD COLUMN parent_task_id VARCHAR(64)"
                    )
                )
        if "scenario_field_config_id" not in cols_b:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE project_task_details ADD COLUMN scenario_field_config_id VARCHAR(64)"
                    )
                )
        if "content" not in cols_b:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE project_task_details ADD COLUMN content TEXT"
                    )
                )
        if "due_date" not in cols_b:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE project_task_details ADD COLUMN due_date DATETIME"
                    )
                )
        if "parent_id" not in cols_b:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE project_task_details ADD COLUMN parent_id VARCHAR(64)"
                    )
                )
        if "task_nature" not in cols_b:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE project_task_details ADD COLUMN task_nature VARCHAR(128)"
                    )
                )
        if "requirement_desc" not in cols_b:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE project_task_details ADD COLUMN requirement_desc TEXT"
                    )
                )
        if "task_outputs" not in cols_b:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE project_task_details ADD COLUMN task_outputs TEXT"
                    )
                )
        if "workday_costhour" not in cols_b:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE project_task_details ADD COLUMN workday_costhour FLOAT"
                    )
                )
                if "workday_duration_minutes" in cols_b:
                    conn.execute(
                        text(
                            "UPDATE project_task_details "
                            "SET workday_costhour = workday_duration_minutes "
                            "WHERE workday_costhour IS NULL AND workday_duration_minutes IS NOT NULL"
                        )
                    )
                    try:
                        conn.execute(text("ALTER TABLE project_task_details DROP COLUMN workday_duration_minutes"))
                    except Exception:
                        pass
        elif "workday_duration_minutes" in cols_b:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "UPDATE project_task_details "
                        "SET workday_costhour = workday_duration_minutes "
                        "WHERE workday_costhour IS NULL AND workday_duration_minutes IS NOT NULL"
                    )
                )
                try:
                    conn.execute(text("ALTER TABLE project_task_details DROP COLUMN workday_duration_minutes"))
                except Exception:
                    pass
        if "workday_costhour" in cols_b:
            _ensure_workday_costhour_float("project_task_details")
        # B 表：级联自定义字段
        if "project_category_1" not in cols_b:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE project_task_details ADD COLUMN project_category_1 VARCHAR(128)"))
        if "vehicle_type_2" not in cols_b:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE project_task_details ADD COLUMN vehicle_type_2 VARCHAR(128)"))
        if "project_name_3" not in cols_b:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE project_task_details ADD COLUMN project_name_3 VARCHAR(256)"))
        if "need_statistic" not in cols_b:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE project_task_details ADD COLUMN need_statistic VARCHAR(8)"))

        # C 表若不存在，create_all 理论上已创建；这里额外做一次兜底检查
        tables = set(inspector.get_table_names() or [])
        if "project_task_overdue_details" not in tables:
            Base.metadata.create_all(bind=engine)
        else:
            cols_c = [c.get("name") for c in inspector.get_columns("project_task_overdue_details")]
            if "business_type" not in cols_c:
                with engine.begin() as conn:
                    conn.execute(
                        text(
                            "ALTER TABLE project_task_overdue_details ADD COLUMN business_type INTEGER"
                        )
                    )
            if "scenario_field_config_id" not in cols_c:
                with engine.begin() as conn:
                    conn.execute(
                        text(
                            "ALTER TABLE project_task_overdue_details ADD COLUMN scenario_field_config_id VARCHAR(64)"
                        )
                    )
            if "content" not in cols_c:
                with engine.begin() as conn:
                    conn.execute(
                        text(
                            "ALTER TABLE project_task_overdue_details ADD COLUMN content TEXT"
                        )
                    )
            if "due_date" not in cols_c:
                with engine.begin() as conn:
                    conn.execute(
                        text(
                            "ALTER TABLE project_task_overdue_details ADD COLUMN due_date DATETIME"
                        )
                    )
            if "task_flow_status_id" not in cols_c:
                with engine.begin() as conn:
                    conn.execute(
                        text(
                            "ALTER TABLE project_task_overdue_details ADD COLUMN task_flow_status_id INTEGER"
                        )
                    )
            if "parent_id" not in cols_c:
                with engine.begin() as conn:
                    conn.execute(
                        text(
                            "ALTER TABLE project_task_overdue_details ADD COLUMN parent_id VARCHAR(64)"
                        )
                    )
            if "task_nature" not in cols_c:
                with engine.begin() as conn:
                    conn.execute(
                        text(
                            "ALTER TABLE project_task_overdue_details ADD COLUMN task_nature VARCHAR(128)"
                        )
                    )
            if "workday_costhour" not in cols_c:
                with engine.begin() as conn:
                    conn.execute(
                        text(
                            "ALTER TABLE project_task_overdue_details ADD COLUMN workday_costhour FLOAT"
                        )
                    )
                    if "workday_duration_minutes" in cols_c:
                        conn.execute(
                            text(
                                "UPDATE project_task_overdue_details "
                                "SET workday_costhour = workday_duration_minutes "
                                "WHERE workday_costhour IS NULL AND workday_duration_minutes IS NOT NULL"
                            )
                        )
                        try:
                            conn.execute(text("ALTER TABLE project_task_overdue_details DROP COLUMN workday_duration_minutes"))
                        except Exception:
                            pass
            elif "workday_duration_minutes" in cols_c:
                with engine.begin() as conn:
                    conn.execute(
                        text(
                            "UPDATE project_task_overdue_details "
                            "SET workday_costhour = workday_duration_minutes "
                            "WHERE workday_costhour IS NULL AND workday_duration_minutes IS NOT NULL"
                        )
                    )
                    try:
                        conn.execute(text("ALTER TABLE project_task_overdue_details DROP COLUMN workday_duration_minutes"))
                    except Exception:
                        pass
            if "workday_costhour" in cols_c:
                _ensure_workday_costhour_float("project_task_overdue_details")
            # C 表：级联自定义字段
            if "project_category_1" not in cols_c:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE project_task_overdue_details ADD COLUMN project_category_1 VARCHAR(128)"))
            if "vehicle_type_2" not in cols_c:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE project_task_overdue_details ADD COLUMN vehicle_type_2 VARCHAR(128)"))
            if "project_name_3" not in cols_c:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE project_task_overdue_details ADD COLUMN project_name_3 VARCHAR(256)"))
            if "need_statistic" not in cols_c:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE project_task_overdue_details ADD COLUMN need_statistic VARCHAR(8)"))

        # B2 表字段补齐（program_issue_detail）
        if "program_issue_detail" in tables:
            cols_b2 = [c.get("name") for c in inspector.get_columns("program_issue_detail")]
            if "parent_id" not in cols_b2:
                with engine.begin() as conn:
                    conn.execute(
                        text(
                            "ALTER TABLE program_issue_detail ADD COLUMN parent_id VARCHAR(64)"
                        )
                    )
            if "task_nature" not in cols_b2:
                with engine.begin() as conn:
                    conn.execute(
                        text(
                            "ALTER TABLE program_issue_detail ADD COLUMN task_nature VARCHAR(128)"
                        )
                    )
            if "workday_costhour" not in cols_b2:
                with engine.begin() as conn:
                    conn.execute(
                        text(
                            "ALTER TABLE program_issue_detail ADD COLUMN workday_costhour FLOAT"
                        )
                    )
                    # 旧数据迁移：若历史字段有值，回填到新字段。
                    if "workday_duration_minutes" in cols_b2:
                        conn.execute(
                            text(
                                "UPDATE program_issue_detail "
                                "SET workday_costhour = workday_duration_minutes "
                                "WHERE workday_costhour IS NULL AND workday_duration_minutes IS NOT NULL"
                            )
                        )
                        try:
                            conn.execute(text("ALTER TABLE program_issue_detail DROP COLUMN workday_duration_minutes"))
                        except Exception:
                            pass
            elif "workday_duration_minutes" in cols_b2:
                with engine.begin() as conn:
                    conn.execute(
                        text(
                            "UPDATE program_issue_detail "
                            "SET workday_costhour = workday_duration_minutes "
                            "WHERE workday_costhour IS NULL AND workday_duration_minutes IS NOT NULL"
                        )
                    )
                    try:
                        conn.execute(text("ALTER TABLE program_issue_detail DROP COLUMN workday_duration_minutes"))
                    except Exception:
                        pass
            if "workday_costhour" in cols_b2:
                _ensure_workday_costhour_float("program_issue_detail")
            # B2 表 (program_issue_detail)：级联自定义字段
            if "project_catagory_1" not in cols_b2:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE program_issue_detail ADD COLUMN project_catagory_1 VARCHAR(128)"))
            if "project_catagory_2" not in cols_b2:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE program_issue_detail ADD COLUMN project_catagory_2 VARCHAR(128)"))
            if "project_catagory_3" not in cols_b2:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE program_issue_detail ADD COLUMN project_catagory_3 VARCHAR(256)"))
            if "need_statistic" not in cols_b2:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE program_issue_detail ADD COLUMN need_statistic VARCHAR(8)"))
            for column, column_type in (
                ("problem_type_1", "VARCHAR(128)"),
                ("problem_type_2", "VARCHAR(128)"),
                ("vehicle_1", "VARCHAR(128)"),
                ("vehicle_2", "VARCHAR(128)"),
                ("problem_note_info_1", "VARCHAR(128)"),
                ("problem_note_info_2", "VARCHAR(128)"),
                ("problem_note_info_3", "VARCHAR(256)"),
                ("cause_level_1", "VARCHAR(128)"),
                ("cause_level_2", "VARCHAR(128)"),
                ("cause_level_3", "VARCHAR(256)"),
                ("software_version", "VARCHAR(128)"),
            ):
                if column not in cols_b2:
                    with engine.begin() as conn:
                        conn.execute(text(f"ALTER TABLE program_issue_detail ADD COLUMN {column} {column_type}"))

        # user_character 表字段补齐（无迁移环境下避免缺列导致启动失败）
        try:
            cols_user = {c.get("name") for c in inspector.get_columns("user_character")}
            with engine.begin() as conn:
                if "team_code" not in cols_user:
                    conn.execute(text("ALTER TABLE user_character ADD COLUMN team_code VARCHAR(64)"))
                if "job_role_code" not in cols_user:
                    conn.execute(text("ALTER TABLE user_character ADD COLUMN job_role_code VARCHAR(64)"))
                if "is_nav_lead" not in cols_user:
                    conn.execute(
                        text(
                            "ALTER TABLE user_character ADD COLUMN is_nav_lead BOOLEAN NOT NULL DEFAULT 0"
                        )
                    )
                if "is_servo_lead" not in cols_user:
                    conn.execute(
                        text(
                            "ALTER TABLE user_character ADD COLUMN is_servo_lead BOOLEAN NOT NULL DEFAULT 0"
                        )
                    )
                if "is_p3_lead" not in cols_user:
                    conn.execute(
                        text(
                            "ALTER TABLE user_character ADD COLUMN is_p3_lead BOOLEAN NOT NULL DEFAULT 0"
                        )
                    )
                if "union_id" not in cols_user:
                    conn.execute(
                        text("ALTER TABLE user_character ADD COLUMN union_id VARCHAR(128)")
                    )
                # Data backfill is intentionally not performed at startup.
                # base.organization.migration owns all legacy-data changes so
                # dry-run, audit and the historical team_id=3 ambiguity remain
                # visible to operators.
        except Exception as exc:
            raise RuntimeError("failed to prepare user_character organization columns") from exc

        # member_attendance 表字段补齐：保存每位成员按季度录入的法定带薪假。
        try:
            cols_attendance = {c.get("name") for c in inspector.get_columns("member_attendance")}
            if "team_code" not in cols_attendance:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE member_attendance ADD COLUMN team_code VARCHAR(64)"))
            if "statutory_holiday_days" not in cols_attendance:
                with engine.begin() as conn:
                    conn.execute(
                        text(
                            "ALTER TABLE member_attendance "
                            "ADD COLUMN statutory_holiday_days FLOAT NOT NULL DEFAULT 0"
                        )
                    )
            if "effective_work_days" not in cols_attendance:
                with engine.begin() as conn:
                    conn.execute(
                        text(
                            "ALTER TABLE member_attendance "
                            "ADD COLUMN effective_work_days FLOAT NOT NULL DEFAULT 0"
                        )
                    )
        except Exception:
            # 不阻断服务启动；缺列时接口会返回明确错误，便于手工迁移。
            pass
    except Exception:
        # 不阻断服务启动：字段不存在/表不存在由上层业务容错
        pass

    # 首次初始化：写入简单配置记录（当前默认配置）
    # 注意：生产环境建议使用迁移工具或显式初始化脚本。
    #
    # 这里的 seed 设计为“清单式”，便于你一眼看清初始化内容。
    try:
        session = SessionLocal()
        try:
            # ===== seed: config 表默认值（type -> value）=====
            _now = datetime.now(timezone.utc)
            _q_end_month = ((_now.month - 1) // 3 + 1) * 3
            if _q_end_month == 12:
                _next_q_first = datetime(_now.year + 1, 1, 1, tzinfo=timezone.utc)
            else:
                _next_q_first = datetime(_now.year, _q_end_month + 1, 1, tzinfo=timezone.utc)
            _q_end_day = (_next_q_first - timedelta(days=1)).day
            start_dt = datetime(_now.year, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
            end_dt = datetime(_now.year, _q_end_month, _q_end_day, 23, 59, 59, tzinfo=timezone.utc)
            default_config_seed = {
                # 时间范围（动态计算：年初 ~ 当前季度末）
                "start_time": start_dt.isoformat(),
                "end_time": end_dt.isoformat(),
                # job_role_code -> coefficient（工时折算系数映射）
                "workhour_role_coefficients": '{"TEAM_LEAD":0.4,"SOFTWARE_ENGINEER":0.8,"SOFTWARE_APPLICATION_ENGINEER":0.8,"APPLICATION_ENGINEER":1.0,"ALGORITHM_ENGINEER":0.8,"INTERN":0.5,"SYSTEM_ADMIN":0.4}',
                # UI 展示“上次更新时间”（固定为 1970，避免每次启动都更新时间）
                "last_update_time": "1970-01-01T00:00:00+00:00",
                # 自动更新配置
                "is_auto_update": "0",
                "auto_update_time": "09:00",
                # tagId -> business_type（0=产品，1=研发，2=订单）
                # 命中规则：按 tagIds 顺序取第一个命中的类型。
                "business_type_tag_mapping": '{"65264cfd697b6b909485bcbc":0,"65264cf79ed530912c3edf0f":1,"65264d01495638aacac3a9f9":2}',
                # taskflowStatusId -> task_flow_status_id（从 0 开始）
                "task_flow_status_mapping": '{"680a31478c1bdfc448d36ed0":0,"647854bcd999c893061ef89b":1,"67fe5c1f142821dbe1328ddf":2,"64785656c6215fd933a96631":3,"647854bcd999c893061ef89c":4,"64785656c6215fd933a96634":5}',
            }
            preserve_existing_keys = {
                "start_time",
                "end_time",
                "last_update_time",
                # 保留数据库中已维护的系数映射，重启不覆盖
                "workhour_role_coefficients",
            }

            def _ensure(cfg_type: str, value: str):
                existing = (
                    session.query(DbConfig)
                    .filter(DbConfig.type_ == cfg_type)
                    .first()
                )
                if existing:
                    # 时间相关配置若已存在，保留现值，不在初始化阶段覆盖。
                    if cfg_type in preserve_existing_keys:
                        return
                    if existing.value != value:
                        existing.value = value
                    return
                session.add(DbConfig(type_=cfg_type, value=value, brief=None))

            for k, v in default_config_seed.items():
                _ensure(k, v)

            session.commit()
        finally:
            session.close()
    except Exception as e:
        # 初始化失败不应阻断服务启动；便于你排查 DB 权限/环境配置问题
        print("[init_db] config init failed:", repr(e))
        pass

    # ── knowledge base FTS index (on kb_engine) ──────────────────
    try:
        from ai.knowledge.models import create_kb_fts
        create_kb_fts(kb_engine)
    except Exception:
        pass


def init_db() -> None:
    """
    兼容旧调用点：仅执行 init（不包含 drop/reset）。
    """
    init_database()


def get_session():
    """获取当前线程会话（用完需 close 或在请求结束 teardown）。"""
    return SessionLocal()


def get_perf_session():
    """获取绩效专用库的会话。"""
    return PerfSessionLocal()


def get_kb_session():
    """获取知识库专用库的会话。"""
    return KbSessionLocal()
