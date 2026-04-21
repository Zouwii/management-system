from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session

from db.config import DATABASE_URI, PERF_DATABASE_URI
from db.orm import Base  # 导入即注册 ProjectTask 等到 Base.metadata

# SQLite 下多线程需 check_same_thread=False（Flask 每请求一线程）
_main_connect_args = {}
if DATABASE_URI.startswith("sqlite"):
    _main_connect_args["check_same_thread"] = False

_perf_connect_args = {}
if PERF_DATABASE_URI.startswith("sqlite"):
    _perf_connect_args["check_same_thread"] = False

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


def _table_registry():
    """
    表注册清单（可视化管理，类似 Go 的 createSQLs/dropSQLs 列表）。
    """
    # 延迟导入以避免循环
    from db.orm import (
        Config as DbConfig,
        NavPerfQuarterResult,
        ProgramIssue,
        ProgramIssueDetail,
        ProjectTask,
        ProjectTaskDetail,
        ProjectTaskOverdueDetail,
        ServoPerfQuarterResult,
        SyncRun,
        UpdateLock,
        UserCharacter as DbUserCharacter,
    )

    main_tables = [
        ("project_tasks", ProjectTask.__table__),
        ("program_issue", ProgramIssue.__table__),
        ("project_task_details", ProjectTaskDetail.__table__),
        ("program_issue_detail", ProgramIssueDetail.__table__),
        ("project_task_overdue_details", ProjectTaskOverdueDetail.__table__),
        ("sync_runs", SyncRun.__table__),
        ("config", DbConfig.__table__),
        ("update_locks", UpdateLock.__table__),
        ("user_character", DbUserCharacter.__table__),
    ]
    perf_tables = [
        ("nav_perf_quarter_result", NavPerfQuarterResult.__table__),
        ("servo_perf_quarter_result", ServoPerfQuarterResult.__table__),
    ]
    return main_tables, perf_tables


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


def init_database() -> None:
    """
    数据库初始化入口（仅 init，不做 drop）：
    - create tables if not exists（主库 + 绩效库）
    - seed 默认配置（config 表、user_character 初始数据等）

    设计目标：初始化内容“可视化、可读、可维护”。
    """
    main_tables, perf_tables = _table_registry()
    # seed 阶段会直接使用这两个 ORM 模型
    from db.orm import Config as DbConfig, UserCharacter as DbUserCharacter

    print("[init_db] creating tables (no drop) ...")
    _execute_table_ops(engine, main_tables, "create")
    _execute_table_ops(perf_engine, perf_tables, "create")

    # 兼容无迁移环境：尝试为 B/C 表补齐新字段/新表（SQLite 场景常见）
    try:
        from sqlalchemy import inspect, text

        inspector = inspect(engine)
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
        if "workday_duration_minutes" not in cols_b:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE project_task_details ADD COLUMN workday_duration_minutes INTEGER"
                    )
                )

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
            if "workday_duration_minutes" not in cols_c:
                with engine.begin() as conn:
                    conn.execute(
                        text(
                            "ALTER TABLE project_task_overdue_details ADD COLUMN workday_duration_minutes INTEGER"
                        )
                    )

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
            if "workday_duration_minutes" not in cols_b2:
                with engine.begin() as conn:
                    conn.execute(
                        text(
                            "ALTER TABLE program_issue_detail ADD COLUMN workday_duration_minutes INTEGER"
                        )
                    )

        # user_character 表字段补齐（无迁移环境下避免缺列导致启动失败）
        try:
            cols_user = {c.get("name") for c in inspector.get_columns("user_character")}
            with engine.begin() as conn:
                if "team_id" not in cols_user:
                    conn.execute(text("ALTER TABLE user_character ADD COLUMN team_id VARCHAR(64)"))
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
        except Exception:
            # 不阻断服务启动；由上层业务容错或你手工执行迁移
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
            start_dt = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
            end_dt = datetime(2026, 3, 31, 23, 59, 59, tzinfo=timezone.utc)
            default_config_seed = {
                # 时间范围（和前端默认保持一致）
                "start_time": start_dt.isoformat(),
                "end_time": end_dt.isoformat(),
                # character -> coefficient（工时折算系数映射）
                "workhour_character_coefficients": '{"0":0.4,"1":0.7,"2":0.7,"3":1.0,"4":0.7}',
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
                "workhour_character_coefficients",
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

            # 初始化 user_character：把 ids.json 中的用户先落库
            # 你之后可以直接在数据库里维护 character/team_id/is_nav_lead/is_servo_lead。
            try:
                from dingtalk_client import get_config_user_meta

                user_meta = get_config_user_meta()
                for name, meta in (user_meta or {}).items():
                    nm = str(name)
                    uid = str((meta or {}).get("userId") or "").strip()
                    if not uid:
                        continue
                    existing_u = (
                        session.query(DbUserCharacter)
                        .filter(DbUserCharacter.user_id == uid)
                        .first()
                    )
                    if existing_u:
                        # 已有记录不覆盖，避免 init_db 把你手工维护的角色/组别改回去。
                        continue
                    else:
                        init_character = int((meta or {}).get("character", 0) or 0)
                        session.add(
                            DbUserCharacter(
                                user_id=uid,
                                name=nm,
                                character=init_character,
                                team_id=str((meta or {}).get("team_id")) if (meta or {}).get("team_id") is not None else None,
                                is_nav_lead=bool((meta or {}).get("is_nav_lead", False)),
                                is_servo_lead=bool((meta or {}).get("is_servo_lead", False)),
                            )
                        )
            except Exception:
                # IDs 初始化失败不阻断服务启动
                pass
            session.commit()
        finally:
            session.close()
    except Exception as e:
        # 初始化失败不应阻断服务启动；便于你排查 DB 权限/环境配置问题
        print("[init_db] config init failed:", repr(e))
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
