"""SQLAlchemy ORM models for knowledge base documents and chunks.

These models belong to a separate KB database (default: kb_storage),
using KbBase instead of the main Base from base.db.orm.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class KbBase(DeclarativeBase):
    """Declarative base for knowledge-base tables (kb_storage database)."""
    pass


class KbNode(KbBase):
    """A 表 — 目录树快照（FOLDER + FILE）"""
    __tablename__ = "kb_nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    node_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True, unique=True)
    workspace_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    parent_id: Mapped[str] = mapped_column(String(128), default="", index=True)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    node_type: Mapped[str] = mapped_column(String(16), nullable=False)    # FOLDER / FILE
    category: Mapped[str] = mapped_column(String(16), default="")         # ALIDOC / WORKBOOK / OTHER
    has_children: Mapped[bool] = mapped_column(default=False)
    depth: Mapped[int] = mapped_column(Integer, default=0)
    breadcrumb: Mapped[str] = mapped_column(String(1024), default="")
    remote_modified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sync_status: Mapped[str] = mapped_column(String(16), default="pending")  # pending / synced / failed
    sync_error: Mapped[str] = mapped_column(String(500), default="")
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc))


class KbDocument(KbBase):
    """B 表 — 文档正文（仅 FILE 节点的内容）"""
    __tablename__ = "kb_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    node_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True, unique=True)
    workspace_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    content: Mapped[str] = mapped_column(MEDIUMTEXT, default="")
    raw_json: Mapped[str] = mapped_column(MEDIUMTEXT, default="")
    error_code: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    fetch_status: Mapped[str] = mapped_column(String(16), default="pending")  # pending / success / failed
    fail_reason: Mapped[str] = mapped_column(String(500), default="")
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc))


class KbChunk(KbBase):
    __tablename__ = "kb_chunks"
    __table_args__ = (
        Index("idx_kb_chunks_doc", "doc_id", "chunk_index"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doc_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


# ── FTS index creation (database-aware) ──────────────────────────

FTS5_CREATE_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS kb_chunks_fts USING fts5(
    content, content=kb_chunks, content_rowid=id
);
"""

MYSQL_FTS_SQL = """
ALTER TABLE kb_chunks ADD FULLTEXT INDEX ft_kb_chunks_content (content) WITH PARSER ngram;
"""


def create_kb_fts(engine=None) -> None:
    """Create full-text search index on kb_chunks.content.

    SQLite: FTS5 virtual table (external content mode).
    MySQL:  FULLTEXT INDEX (built-in InnoDB full-text).

    If engine is None, uses the KB database engine (kb_engine).
    """
    from sqlalchemy import text

    if engine is None:
        from base.db.engine import kb_engine
        engine = kb_engine

    dialect = engine.dialect.name
    with engine.begin() as conn:
        if dialect == "sqlite":
            try:
                conn.execute(text(FTS5_CREATE_SQL))
            except Exception:
                pass
        elif dialect == "mysql":
            try:
                conn.execute(text(MYSQL_FTS_SQL))
            except Exception:
                pass


def drop_kb_fts(engine=None) -> None:
    """Drop FTS index (for rebuild scenarios).

    If engine is None, uses the KB database engine (kb_engine).
    """
    from sqlalchemy import text

    if engine is None:
        from base.db.engine import kb_engine
        engine = kb_engine

    dialect = engine.dialect.name
    with engine.begin() as conn:
        if dialect == "sqlite":
            try:
                conn.execute(text("DROP TABLE IF EXISTS kb_chunks_fts"))
            except Exception:
                pass
        elif dialect == "mysql":
            try:
                conn.execute(text("ALTER TABLE kb_chunks DROP INDEX ft_kb_chunks_content"))
            except Exception:
                pass
