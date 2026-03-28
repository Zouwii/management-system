# -*- coding: utf-8 -*-
"""
tb_tool_bt 独立数据库（与 tb_tool_backend 的 teambition.db 无关）。

默认：backend/data/tb_tool_bt.db（SQLite）

MySQL：TB_TOOL_BT_USE_MYSQL=1，库名默认 tb_tool_bt（可用 TB_TOOL_BT_DB_NAME 覆盖）。
仍支持旧环境变量名 TB_TOOL_B1_*。

或整条：TB_TOOL_BT_DATABASE_URI=mysql+pymysql://user:pass@host:3306/tb_tool_bt?charset=utf8mb4
"""

from db.engine import engine, get_session, init_db, SessionLocal

__all__ = ["engine", "get_session", "init_db", "SessionLocal"]
