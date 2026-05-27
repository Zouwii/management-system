"""SQLAlchemy ORM models for knowledge base documents and chunks."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from db.orm import Base


class KbDocument(Base):
    __tablename__ = "kb_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doc_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    node_type: Mapped[str] = mapped_column(String(16), default="FILE")
    parent_id: Mapped[str] = mapped_column(String(128), default="")
    content: Mapped[str] = mapped_column(Text, default="")
    raw_json: Mapped[str] = mapped_column(Text, default="")
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class KbChunk(Base):
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


def create_kb_fts(engine) -> None:
    """Create full-text search index on kb_chunks.content.

    SQLite: FTS5 virtual table (external content mode).
    MySQL:  FULLTEXT INDEX (built-in InnoDB full-text).
    """
    from sqlalchemy import text

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


def drop_kb_fts(engine) -> None:
    """Drop FTS index (for rebuild scenarios)."""
    from sqlalchemy import text

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
