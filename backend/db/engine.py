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


def get_session():
    """获取当前线程会话（用完需 close 或在请求结束 teardown）。"""
    return SessionLocal()
