import os
from pathlib import Path
from typing import Optional
from urllib.parse import quote_plus

_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent

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

DEFAULT_MYSQL_DB_NAME = "benti_management"
DEFAULT_PERF_DB_NAME = "perf_quarter_result"
DEFAULT_KB_DB_NAME = "kb_storage"
DEFAULT_ONSITE_DB_NAME = "onsite_problem"
DEFAULT_REQ_POOL_DB_NAME = "req_pool"
DEFAULT_ALGO_DB_NAME = "algo_management"


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

# 知识库专用数据库 URI（kb_documents / kb_chunks；不配置时退回到主库）
_kb_explicit = (env_bt("KB_DATABASE_URI") or "").strip()
if _kb_explicit:
    KB_DATABASE_URI = _kb_explicit
elif (env_bt("USE_MYSQL") or "").lower() in ("1", "true", "yes"):
    user = env_bt("DB_USER", "root") or "root"
    password = env_bt("DB_PASSWORD", "") or ""
    host = env_bt("DB_HOST", "127.0.0.1") or "127.0.0.1"
    port = env_bt("DB_PORT", "3306") or "3306"
    kb_name = env_bt("KB_DB_NAME", DEFAULT_KB_DB_NAME) or DEFAULT_KB_DB_NAME
    KB_DATABASE_URI = (
        f"mysql+pymysql://{quote_plus(user)}:{quote_plus(password)}"
        f"@{host}:{port}/{kb_name}?charset=utf8mb4"
    )
else:
    # SQLite 场景退回主库同一个文件（兼容开发/单机部署）
    KB_DATABASE_URI = DEFAULT_SQLITE_URI

# onsite_problem 数据库 URI
_default_onsite_sqlite_path = _DATA_DIR / "onsite_problem.db"
DEFAULT_ONSITE_SQLITE_URI = f"sqlite:///{_default_onsite_sqlite_path}"

_onsite_explicit = (env_bt("ONSITE_DATABASE_URI") or "").strip()
if _onsite_explicit:
    ONSITE_DATABASE_URI = _onsite_explicit
elif (env_bt("USE_MYSQL") or "").lower() in ("1", "true", "yes"):
    user = env_bt("DB_USER", "root") or "root"
    password = env_bt("DB_PASSWORD", "") or ""
    host = env_bt("DB_HOST", "127.0.0.1") or "127.0.0.1"
    port = env_bt("DB_PORT", "3306") or "3306"
    onsite_name = env_bt("ONSITE_DB_NAME", DEFAULT_ONSITE_DB_NAME) or DEFAULT_ONSITE_DB_NAME
    ONSITE_DATABASE_URI = (
        f"mysql+pymysql://{quote_plus(user)}:{quote_plus(password)}"
        f"@{host}:{port}/{onsite_name}?charset=utf8mb4"
    )
else:
    ONSITE_DATABASE_URI = DEFAULT_ONSITE_SQLITE_URI

# req_pool 数据库 URI
_default_req_pool_sqlite_path = _DATA_DIR / "req_pool.db"
DEFAULT_REQ_POOL_SQLITE_URI = f"sqlite:///{_default_req_pool_sqlite_path}"

_req_pool_explicit = (env_bt("REQ_POOL_DATABASE_URI") or "").strip()
if _req_pool_explicit:
    REQ_POOL_DATABASE_URI = _req_pool_explicit
elif (env_bt("USE_MYSQL") or "").lower() in ("1", "true", "yes"):
    user = env_bt("DB_USER", "root") or "root"
    password = env_bt("DB_PASSWORD", "") or ""
    host = env_bt("DB_HOST", "127.0.0.1") or "127.0.0.1"
    port = env_bt("DB_PORT", "3306") or "3306"
    req_pool_name = env_bt("REQ_POOL_DB_NAME", DEFAULT_REQ_POOL_DB_NAME) or DEFAULT_REQ_POOL_DB_NAME
    REQ_POOL_DATABASE_URI = (
        f"mysql+pymysql://{quote_plus(user)}:{quote_plus(password)}"
        f"@{host}:{port}/{req_pool_name}?charset=utf8mb4"
    )
else:
    REQ_POOL_DATABASE_URI = DEFAULT_REQ_POOL_SQLITE_URI

# 算法组四张 A/B 表专用数据库
_default_algo_sqlite_path = _DATA_DIR / "algo_management.db"
DEFAULT_ALGO_SQLITE_URI = f"sqlite:///{_default_algo_sqlite_path}"

_algo_explicit = (env_bt("ALGO_DATABASE_URI") or "").strip()
if _algo_explicit:
    ALGO_DATABASE_URI = _algo_explicit
elif (env_bt("USE_MYSQL") or "").lower() in ("1", "true", "yes"):
    user = env_bt("DB_USER", "root") or "root"
    password = env_bt("DB_PASSWORD", "") or ""
    host = env_bt("DB_HOST", "127.0.0.1") or "127.0.0.1"
    port = env_bt("DB_PORT", "3306") or "3306"
    algo_name = env_bt("ALGO_DB_NAME", DEFAULT_ALGO_DB_NAME) or DEFAULT_ALGO_DB_NAME
    ALGO_DATABASE_URI = (
        f"mysql+pymysql://{quote_plus(user)}:{quote_plus(password)}"
        f"@{host}:{port}/{algo_name}?charset=utf8mb4"
    )
else:
    ALGO_DATABASE_URI = DEFAULT_ALGO_SQLITE_URI

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
