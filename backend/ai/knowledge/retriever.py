"""Keyword-based chunk retrieval using MySQL FULLTEXT or SQLite FTS5,
plus vector semantic search and hybrid RRF fusion."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import text

from base.db.engine import SessionLocal, PgVectorSessionLocal, engine


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


# ── vector / hybrid search ────────────────────────────────────


def search_vector(
    query: str,
    top_k: int = 10,
    workspace_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Semantic search via pgvector cosine similarity."""
    if not query or not query.strip():
        return []

    from ai.knowledge.embedder import _get_model

    model = _get_model()
    q_emb = model.encode(
        [query.strip()], normalize_embeddings=True, show_progress_bar=False
    )[0]

    # Format as pgvector literal — safe because values are our own floats
    vec_str = "[" + ",".join(str(x) for x in q_emb) + "]"

    pg = PgVectorSessionLocal()
    mysql = SessionLocal()
    try:
        # Step 1: find nearest chunk_ids in pgvector
        pg_sql = text(
            f"SELECT chunk_id, 1 - (embedding <=> '{vec_str}') AS score "
            "FROM chunk_vectors "
            f"ORDER BY embedding <=> '{vec_str}' "
            "LIMIT :limit"
        )
        pg_rows = pg.execute(pg_sql, {"limit": top_k * 2}).fetchall()

        if not pg_rows:
            return []

        score_map = {r[0]: float(r[1] or 0) for r in pg_rows}
        chunk_ids = list(score_map.keys())

        # Step 2: fetch metadata from MySQL
        placeholders = ",".join([f":id_{i}" for i in range(len(chunk_ids))])
        if workspace_id:
            mysql_sql = text(
                f"SELECT c.id, c.doc_id, d.title, c.chunk_index, c.content, "
                f"c.token_count, d.workspace_id "
                f"FROM kb_chunks c JOIN kb_documents d ON c.doc_id = d.doc_id "
                f"WHERE c.id IN ({placeholders}) AND d.workspace_id = :ws_id"
            )
            mrows = mysql.execute(
                mysql_sql,
                {f"id_{i}": cid for i, cid in enumerate(chunk_ids)}
                | {"ws_id": workspace_id},
            ).fetchall()
        else:
            mysql_sql = text(
                f"SELECT c.id, c.doc_id, d.title, c.chunk_index, c.content, "
                f"c.token_count, d.workspace_id "
                f"FROM kb_chunks c JOIN kb_documents d ON c.doc_id = d.doc_id "
                f"WHERE c.id IN ({placeholders})"
            )
            mrows = mysql.execute(
                mysql_sql,
                {f"id_{i}": cid for i, cid in enumerate(chunk_ids)},
            ).fetchall()

        results = [
            {
                "chunk_id": r[0],
                "doc_id": r[1],
                "title": r[2],
                "chunk_index": r[3],
                "content": r[4],
                "score": round(score_map.get(r[0], 0), 4),
                "token_count": r[5],
                "workspace_id": r[6],
            }
            for r in mrows
        ]
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]
    except Exception:
        return []
    finally:
        pg.close()
        mysql.close()


_RRF_K = 60


def search_hybrid(
    query: str,
    top_k: int = 10,
    workspace_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Hybrid search: keyword (FULLTEXT) + vector (cosine), fused via RRF."""
    if not query or not query.strip():
        return []

    # Run both retrievals
    kw_results = search_chunks(query, top_k=top_k * 2, workspace_id=workspace_id)
    vec_results = search_vector(query, top_k=top_k * 2, workspace_id=workspace_id)

    # RRF fusion: score = sum(1 / (k + rank_i))
    rrf: Dict[int, float] = {}
    meta: Dict[int, dict] = {}

    for rank, r in enumerate(kw_results):
        cid = r["chunk_id"]
        rrf[cid] = rrf.get(cid, 0) + 1.0 / (_RRF_K + rank + 1)
        meta[cid] = r

    for rank, r in enumerate(vec_results):
        cid = r["chunk_id"]
        rrf[cid] = rrf.get(cid, 0) + 1.0 / (_RRF_K + rank + 1)
        if cid not in meta:
            meta[cid] = r

    # Sort by RRF score descending
    sorted_ids = sorted(rrf, key=lambda cid: rrf[cid], reverse=True)[:top_k]

    return [
        {**meta[cid], "score": round(rrf[cid], 4)}
        for cid in sorted_ids
    ]
