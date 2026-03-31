from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session

from db.config import DATABASE_URI
from db.orm import Base  # 导入即注册 ProjectTask 等到 Base.metadata

# SQLite 下多线程需 check_same_thread=False（Flask 每请求一线程）
_connect_args = {}
if DATABASE_URI.startswith("sqlite"):
    _connect_args["check_same_thread"] = False

engine = create_engine(
    DATABASE_URI,
    connect_args=_connect_args,
    future=True,
    pool_pre_ping=True,
)

SessionLocal = scoped_session(sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True))


def init_db() -> None:
    """创建所有表（无迁移工具时用于开发；生产建议 Alembic）。"""
    Base.metadata.create_all(bind=engine)

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

        # C 表若不存在，create_all 理论上已创建；这里额外做一次兜底检查
        tables = set(inspector.get_table_names() or [])
        if "project_task_overdue_details" not in tables:
            Base.metadata.create_all(bind=engine)
    except Exception:
        # 不阻断服务启动：字段不存在/表不存在由上层业务容错
        pass

    # 首次初始化：写入简单配置记录（当前默认配置）
    # - type=start_time：value 为当前年份 1/1 00:00:00（ISO 格式）
    # - type=end_time：value 为当前年份 3/31 23:59:59（ISO 格式）
    # 注意：生产环境建议使用迁移工具或显式初始化脚本。
    try:
        from db.orm import Config as DbConfig
        from db.orm import UserCharacter as DbUserCharacter

        session = SessionLocal()
        try:
            # 默认时间区间：固定写入 2026Q1（和前端默认保持一致）
            start_dt = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
            end_dt = datetime(2026, 3, 31, 23, 59, 59, tzinfo=timezone.utc)

            def _ensure(cfg_type: str, value: str):
                existing = (
                    session.query(DbConfig)
                    .filter(DbConfig.type_ == cfg_type)
                    .first()
                )
                if existing:
                    if existing.value != value:
                        existing.value = value
                    return
                session.add(DbConfig(type_=cfg_type, value=value, brief=None))

            _ensure("start_time", start_dt.isoformat())
            _ensure("end_time", end_dt.isoformat())
            # 工时折算系数映射：用于把「有效工作日天数」换算为「预计工时」
            # character -> coefficient
            _ensure(
                "workhour_character_coefficients",
                '{"0":0.4,"1":0.7,"2":0.7,"3":1.0}',
            )

            # last_update_time：用于 UI 展示“上次更新时间”
            # 默认固定为 1970，避免 init_db 每次启动都更新时间。
            _ensure("last_update_time", "1970-01-01T00:00:00+00:00")

            # 自动更新配置：
            # - is_auto_update：开启/关闭开关（字符串形式：1/0）
            # - auto_update_time：每天触发的时间点（HH:MM，本地时间）
            _ensure("is_auto_update", "0")
            _ensure("auto_update_time", "09:00")

            # 初始化 user_character：把 ids.json 中的用户先落库，character 默认 0
            # 你之后可以直接更新 character。
            try:
                from dingtalk_client import get_config_userids, get_config_user_characters

                userids = get_config_userids()
                user_characters = get_config_user_characters()
                for name, user_id in (userids or {}).items():
                    uid = str(user_id)
                    nm = str(name)
                    existing_u = (
                        session.query(DbUserCharacter)
                        .filter(DbUserCharacter.user_id == uid)
                        .first()
                    )
                    if existing_u:
                        if existing_u.name != nm:
                            existing_u.name = nm
                    else:
                        init_character = int(user_characters.get(nm, 0) or 0)
                        session.add(
                            DbUserCharacter(user_id=uid, name=nm, character=init_character)
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


def get_session():
    """获取当前线程会话（用完需 close 或在请求结束 teardown）。"""
    return SessionLocal()
