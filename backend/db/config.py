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
DEFAULT_SQLITE_URI = f"sqlite:///{_default_sqlite_path}"

DEFAULT_MYSQL_DB_NAME = "tb_management"


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
