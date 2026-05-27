import os
from pathlib import Path
from typing import Optional
from urllib.parse import quote_plus

_BACKEND_ROOT = Path(__file__).resolve().parent.parent

# 未启动 Flask 时单独执行 init_db 也能读到 backend/.env
try:
    from dotenv import load_dotenv

    load_dotenv(_BACKEND_ROOT / ".env")
except ImportError:
    pass

_DATA_DIR = _BACKEND_ROOT / "data"
_DATA_DIR.mkdir(parents=True, exist_ok=True)

_default_sqlite_path = _DATA_DIR / "tb_tool_bt.db"
_default_perf_sqlite_path = _DATA_DIR / "tb_perf_quarter.db"
DEFAULT_SQLITE_URI = f"sqlite:///{_default_sqlite_path}"
DEFAULT_PERF_SQLITE_URI = f"sqlite:///{_default_perf_sqlite_path}"

DEFAULT_MYSQL_DB_NAME = "tb_management"
DEFAULT_PERF_DB_NAME = "perf_quarter_result"


def env_bt(name: str, default: Optional[str] = None) -> Optional[str]:
    """优先读 TB_TOOL_BT_*，兼容旧 TB_TOOL_B1_*。"""
    bt = os.getenv(f"TB_TOOL_BT_{name}")
    if bt is not None:
        return bt
    b1 = os.getenv(f"TB_TOOL_B1_{name}")
    if b1 is not None:
        return b1
    return default


def _mysql_uri_from_env() -> str:
    user = env_bt("DB_USER", "root") or "root"
    password = env_bt("DB_PASSWORD", "") or ""
    host = env_bt("DB_HOST", "127.0.0.1") or "127.0.0.1"
    port = env_bt("DB_PORT", "3306") or "3306"
    name = env_bt("DB_NAME", DEFAULT_MYSQL_DB_NAME) or DEFAULT_MYSQL_DB_NAME
    return (
        f"mysql+pymysql://{quote_plus(user)}:{quote_plus(password)}"
        f"@{host}:{port}/{name}?charset=utf8mb4"
    )


_explicit = (env_bt("DATABASE_URI") or "").strip()
if _explicit:
    DATABASE_URI = _explicit
elif (env_bt("USE_MYSQL") or "").lower() in ("1", "true", "yes"):
    DATABASE_URI = _mysql_uri_from_env()
else:
    DATABASE_URI = DEFAULT_SQLITE_URI


# 绩效专用数据库 URI（可与主库不同；未配置时退回到 SQLite 或主库）
_perf_explicit = (env_bt("PERF_DATABASE_URI") or "").strip()
if _perf_explicit:
    PERF_DATABASE_URI = _perf_explicit
elif (env_bt("USE_MYSQL") or "").lower() in ("1", "true", "yes"):
    # 复用主库连接参数，只是库名改为 PERF_DB_NAME
    user = env_bt("DB_USER", "root") or "root"
    password = env_bt("DB_PASSWORD", "") or ""
    host = env_bt("DB_HOST", "127.0.0.1") or "127.0.0.1"
    port = env_bt("DB_PORT", "3306") or "3306"
    perf_name = env_bt("PERF_DB_NAME", DEFAULT_PERF_DB_NAME) or DEFAULT_PERF_DB_NAME
    PERF_DATABASE_URI = (
        f"mysql+pymysql://{quote_plus(user)}:{quote_plus(password)}"
        f"@{host}:{port}/{perf_name}?charset=utf8mb4"
    )
else:
    PERF_DATABASE_URI = DEFAULT_PERF_SQLITE_URI

# ── pgvector (PostgreSQL) — embedding vector storage ─────────────

def _pgvector_uri_from_env() -> str:
    host = os.getenv("PGVECTOR_HOST", "127.0.0.1")
    port = os.getenv("PGVECTOR_PORT", "5432")
    user = os.getenv("PGVECTOR_USER", "tb")
    password = os.getenv("PGVECTOR_PASSWORD", "")
    name = os.getenv("PGVECTOR_DB", "kb_vectors")
    return (
        f"postgresql+psycopg2://{quote_plus(user)}:{quote_plus(password)}"
        f"@{host}:{port}/{name}"
    )


_pgv_explicit = (os.getenv("PGVECTOR_DATABASE_URI") or "").strip()
if _pgv_explicit:
    PGVECTOR_DATABASE_URI = _pgv_explicit
else:
    PGVECTOR_DATABASE_URI = _pgvector_uri_from_env()
