"""Keyword-based chunk retrieval using MySQL FULLTEXT or SQLite FTS5."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import text

from db.engine import SessionLocal, engine


def search_chunks(
    query: str,
    top_k: int = 10,
    workspace_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Search kb_chunks via full-text index, joined with kb_documents for metadata.

    MySQL:  MATCH(content) AGAINST(:kw IN NATURAL LANGUAGE MODE)
    SQLite: JOIN kb_chunks_fts WHERE kb_chunks_fts MATCH :kw
    """
    if not query or not query.strip():
        return []

    dialect = engine.dialect.name
    db = SessionLocal()
    try:
        if dialect == "mysql":
            rows = _search_mysql(db, query.strip(), top_k, workspace_id)
        else:
            rows = _search_sqlite(db, query.strip(), top_k, workspace_id)

        return [
            {
                "chunk_id": r[0],
                "doc_id": r[1],
                "title": r[2],
                "chunk_index": r[3],
                "content": r[4],
                "score": round(float(r[5] or 0), 4),
                "token_count": r[6],
                "workspace_id": r[7],
            }
            for r in rows
        ]
    finally:
        db.close()


def _search_mysql(db, query: str, top_k: int, workspace_id: Optional[str]) -> list:
    if workspace_id:
        sql = text(
            "SELECT c.id, c.doc_id, d.title, c.chunk_index, c.content, "
            "MATCH(c.content) AGAINST(:kw IN NATURAL LANGUAGE MODE) AS score, "
            "c.token_count, d.workspace_id "
            "FROM kb_chunks c JOIN kb_documents d ON c.doc_id = d.doc_id "
            "WHERE MATCH(c.content) AGAINST(:kw IN NATURAL LANGUAGE MODE) "
            "AND d.workspace_id = :ws_id "
            "ORDER BY score DESC LIMIT :limit"
        )
        rows = db.execute(sql, {"kw": query, "ws_id": workspace_id, "limit": top_k}).fetchall()
    else:
        sql = text(
            "SELECT c.id, c.doc_id, d.title, c.chunk_index, c.content, "
            "MATCH(c.content) AGAINST(:kw IN NATURAL LANGUAGE MODE) AS score, "
            "c.token_count, d.workspace_id "
            "FROM kb_chunks c JOIN kb_documents d ON c.doc_id = d.doc_id "
            "WHERE MATCH(c.content) AGAINST(:kw IN NATURAL LANGUAGE MODE) "
            "ORDER BY score DESC LIMIT :limit"
        )
        rows = db.execute(sql, {"kw": query, "limit": top_k}).fetchall()
    return list(rows)


def _search_sqlite(db, query: str, top_k: int, workspace_id: Optional[str]) -> list:
    # SQLite FTS5 syntax: escape double-quotes in query, wrap in double-quotes
    fts_query = f'"{query.replace(chr(34), chr(34)+chr(34))}"'
    if workspace_id:
        sql = text(
            "SELECT c.id, c.doc_id, d.title, c.chunk_index, c.content, "
            "bm25(kb_chunks_fts) AS score, c.token_count, d.workspace_id "
            "FROM kb_chunks c "
            "JOIN kb_documents d ON c.doc_id = d.doc_id "
            "JOIN kb_chunks_fts fts ON c.id = fts.id "
            "WHERE kb_chunks_fts MATCH :kw AND d.workspace_id = :ws_id "
            "ORDER BY score LIMIT :limit"
        )
        rows = db.execute(sql, {"kw": fts_query, "ws_id": workspace_id, "limit": top_k}).fetchall()
    else:
        sql = text(
            "SELECT c.id, c.doc_id, d.title, c.chunk_index, c.content, "
            "bm25(kb_chunks_fts) AS score, c.token_count, d.workspace_id "
            "FROM kb_chunks c "
            "JOIN kb_documents d ON c.doc_id = d.doc_id "
            "JOIN kb_chunks_fts fts ON c.id = fts.id "
            "WHERE kb_chunks_fts MATCH :kw "
            "ORDER BY score LIMIT :limit"
        )
        rows = db.execute(sql, {"kw": fts_query, "limit": top_k}).fetchall()
    return list(rows)
