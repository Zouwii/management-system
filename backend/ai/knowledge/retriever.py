"""Keyword-based chunk retrieval using MySQL FULLTEXT or SQLite FTS5,
plus vector semantic search and hybrid RRF fusion."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import text

from base.db.engine import KbSessionLocal, PgVectorSessionLocal, kb_engine


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

    dialect = kb_engine.dialect.name
    db = KbSessionLocal()
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
            "FROM kb_chunks c JOIN kb_documents d ON c.doc_id = d.node_id "
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
            "FROM kb_chunks c JOIN kb_documents d ON c.doc_id = d.node_id "
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
            "JOIN kb_documents d ON c.doc_id = d.node_id "
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
            "JOIN kb_documents d ON c.doc_id = d.node_id "
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

    from ai.knowledge.embedder import _get_model, is_model_ready

    if not is_model_ready():
        return []  # model not loaded yet, skip vector search

    model = _get_model()
    q_emb = model.encode(
        [query.strip()], normalize_embeddings=True, show_progress_bar=False
    )[0]

    # Format as pgvector literal — safe because values are our own floats
    vec_str = "[" + ",".join(str(x) for x in q_emb) + "]"

    pg = PgVectorSessionLocal()
    kb = KbSessionLocal()
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
                f"FROM kb_chunks c JOIN kb_documents d ON c.doc_id = d.node_id "
                f"WHERE c.id IN ({placeholders}) AND d.workspace_id = :ws_id"
            )
            mrows = kb.execute(
                mysql_sql,
                {f"id_{i}": cid for i, cid in enumerate(chunk_ids)}
                | {"ws_id": workspace_id},
            ).fetchall()
        else:
            mysql_sql = text(
                f"SELECT c.id, c.doc_id, d.title, c.chunk_index, c.content, "
                f"c.token_count, d.workspace_id "
                f"FROM kb_chunks c JOIN kb_documents d ON c.doc_id = d.node_id "
                f"WHERE c.id IN ({placeholders})"
            )
            mrows = kb.execute(
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
        kb.close()


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


def search_with_rerank(
    query: str,
    top_k: int = 20,
    workspace_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Hybrid 检索 + Cross-Encoder 重排。

    1. Hybrid RRF 召回 top_k 个候选
    2. bge-reranker-base 重排（重新打分排序）
    3. 返回重排后的 top_k 结果

    精度提升约 +26pp Recall@5（基于 26 题对照实验）。
    """
    results = search_hybrid(query, top_k=top_k, workspace_id=workspace_id)
    if len(results) <= 1:
        return results

    try:
        from ai.knowledge.reranker import rerank
        return rerank(query, results)
    except Exception:
        import logging
        logging.getLogger(__name__).exception("rerank failed, falling back to hybrid only")
        return results


# ══════════════════════════════════════════════════════════════════════
# RAG v3: leaf retrieval + parent-child expansion
# ══════════════════════════════════════════════════════════════════════

def _expand_parents(db, leaf_chunk_ids: List[int]) -> Dict[int, dict]:
    """Fetch parent chunks for given leaf chunk IDs.

    Returns {leaf_chunk_id: parent_chunk_dict, ...}.
    Only returns parents that actually exist (parent_id is not NULL).
    """
    if not leaf_chunk_ids:
        return {}

    from ai.knowledge.models import KbChunk

    # Get leaf chunks with their parent_ids
    leaves = db.query(KbChunk.id, KbChunk.parent_id).filter(
        KbChunk.id.in_(leaf_chunk_ids),
        KbChunk.parent_id.isnot(None),
    ).all()

    parent_ids = [p for _, p in leaves if p]
    if not parent_ids:
        return {}

    # Fetch parent chunks
    parents = {
        p.id: p for p in db.query(KbChunk).filter(KbChunk.id.in_(parent_ids)).all()
    }

    return {
        leaf_id: {
            "chunk_id": parents[parent_id].id,
            "doc_id": parents[parent_id].doc_id,
            "content": parents[parent_id].content,
            "token_count": parents[parent_id].token_count,
            "depth": 0,
            "chunk_type": "parent",
            "section_path": parents[parent_id].section_path or "",
        }
        for leaf_id, parent_id in leaves
        if parent_id in parents
    }


def _expand_siblings(db, leaf_chunk_ids: List[int], radius: int = 1) -> Dict[int, List[dict]]:
    """Fetch adjacent leaf chunks (±radius) in the same document.

    Returns {leaf_chunk_id: [sibling_chunk_dict, ...]}.
    Siblings are ordered by chunk_index.
    """
    if not leaf_chunk_ids:
        return {}

    from ai.knowledge.models import KbChunk

    # Get leaf chunks for doc_id + chunk_index context
    leaves = db.query(KbChunk).filter(KbChunk.id.in_(leaf_chunk_ids)).all()
    if not leaves:
        return {}

    # Collect all (doc_id, chunk_index_range) pairs
    ranges: Dict[str, List[tuple]] = {}  # doc_id -> [(center_idx, leaf_id), ...]
    leaf_map: Dict[str, tuple] = {}       # doc_id -> (doc_id, title) for metadata

    for l in leaves:
        ranges.setdefault(l.doc_id, []).append((l.chunk_index, l.id))

    # Fetch document titles
    from ai.knowledge.models import KbDocument
    doc_ids = list(ranges.keys())
    docs = {d.node_id: d.title for d in db.query(KbDocument).filter(
        KbDocument.node_id.in_(doc_ids)
    ).all()}

    # For each doc, find the min/max chunk_index ranges
    all_ranges: List[tuple] = []  # (doc_id, start_idx, end_idx)
    for doc_id, entries in ranges.items():
        for center_idx, leaf_id in entries:
            all_ranges.append((doc_id, center_idx - radius, center_idx + radius))

    if not all_ranges:
        return {}

    # Fetch sibling chunks — one query per doc for simplicity
    siblings: Dict[int, List[dict]] = {}
    seen_docs = set()

    for doc_id, start_idx, end_idx in all_ranges:
        if doc_id in seen_docs:
            continue
        seen_docs.add(doc_id)

        # Find overall min/max for this doc
        doc_entries = ranges[doc_id]
        min_idx = min(e[0] for e in doc_entries) - radius
        max_idx = max(e[0] for e in doc_entries) + radius

        sib_rows = db.query(KbChunk).filter(
            KbChunk.doc_id == doc_id,
            KbChunk.depth == 1,  # only leaf siblings
            KbChunk.chunk_index >= min_idx,
            KbChunk.chunk_index <= max_idx,
        ).order_by(KbChunk.chunk_index).all()

        doc_title = docs.get(doc_id, "")

        for leaf_id in [e[1] for e in doc_entries]:
            center_idx = next(e[0] for e in doc_entries if e[1] == leaf_id)
            sib_list = []
            for s in sib_rows:
                if abs(s.chunk_index - center_idx) <= radius and s.id != leaf_id:
                    sib_list.append({
                        "chunk_id": s.id,
                        "doc_id": s.doc_id,
                        "title": doc_title,
                        "chunk_index": s.chunk_index,
                        "content": s.content,
                        "token_count": s.token_count,
                        "depth": s.depth,
                        "chunk_type": s.chunk_type,
                        "section_path": s.section_path or "",
                    })
            siblings[leaf_id] = sib_list

    return siblings


def search_v3(
    query: str,
    top_k: int = 10,
    workspace_id: Optional[str] = None,
    *,
    expand_parents: bool = True,
    expand_siblings: bool = True,
    sibling_radius: int = 1,
) -> Dict[str, Any]:
    """RAG v3 retrieval: leaf search → parent + sibling expansion.

    1. Hybrid RRF search on leaf chunks (depth=1) only
    2. For each hit, expand to parent chunk (if exists)
    3. For each hit, expand to ±sibling_radius adjacent leaves
    4. Deduplicate, format for LLM context

    Returns {
        "hits": [...],           # original leaf hits with scores
        "expanded": [...],       # deduplicated context chunks (leaf + parent + siblings)
        "context": str,          # assembled LLM-ready context
        "stats": {...},          # hit count, expansion stats
    }
    """
    if not query or not query.strip():
        return {"hits": [], "expanded": [], "context": "", "stats": {}}

    # Step 1: search — try hybrid, fall back to keyword-only if model not ready
    # Fetch 2x candidates for reranker to have enough pool
    recall_k = max(top_k * 2, 20)

    hits = []
    try:
        hits = search_hybrid(query, top_k=recall_k, workspace_id=workspace_id)
    except Exception:
        pass

    if not hits:
        try:
            hits = search_chunks(query, top_k=recall_k, workspace_id=workspace_id)
        except Exception:
            pass

    if not hits:
        return {"hits": [], "expanded": [], "context": "", "stats": {"hits": 0}}

    # Step 2: filter to leaf chunks, enrich with DB metadata
    db = KbSessionLocal()
    try:
        all_ids = [h["chunk_id"] for h in hits]
        from ai.knowledge.models import KbChunk

        chunk_rows = {
            r.id: r for r in db.query(KbChunk).filter(KbChunk.id.in_(all_ids)).all()
        }

        leaf_hits = []
        for h in hits:
            row = chunk_rows.get(h["chunk_id"])
            if row:
                h["depth"] = row.depth or 0
                h["section_path"] = row.section_path or ""
                h["parent_id"] = row.parent_id
                if row.depth == 1:
                    leaf_hits.append(h)

        if not leaf_hits:
            leaf_hits = [h for h in hits if h.get("depth") == 1]
        if not leaf_hits:
            leaf_hits = hits[:recall_k]

        # Step 3: rerank leaf hits with cross-encoder, take top_k
        rerank_stats = {"candidates": len(leaf_hits), "reranked": False}
        if len(leaf_hits) > 1:
            try:
                from ai.knowledge.reranker import rerank, is_reranker_ready
                if is_reranker_ready():
                    leaf_hits = rerank(query, leaf_hits)
                    rerank_stats["reranked"] = True
            except Exception:
                pass
        leaf_hits = leaf_hits[:top_k]

        # Step 4: expand
        expanded: Dict[int, dict] = {}
        expansion_stats = {"leaf": 0, "parent": 0, "sibling": 0}

        leaf_ids = [h["chunk_id"] for h in leaf_hits]

        # Add leaf hits themselves
        for h in leaf_hits:
            cid = h["chunk_id"]
            if cid not in expanded:
                expanded[cid] = {
                    "chunk_id": cid,
                    "doc_id": h.get("doc_id", ""),
                    "title": h.get("title", ""),
                    "chunk_index": h.get("chunk_index", 0),
                    "content": h.get("content", ""),
                    "token_count": h.get("token_count", 0),
                    "score": h.get("score", 0),
                    "source": "leaf_hit",
                    "depth": h.get("depth", 1),
                    "section_path": h.get("section_path", ""),
                }
                expansion_stats["leaf"] += 1

        # Expand parents
        if expand_parents:
            parents = _expand_parents(db, leaf_ids)
            for leaf_id, parent in parents.items():
                if parent["chunk_id"] not in expanded:
                    expanded[parent["chunk_id"]] = {
                        **parent,
                        "score": 0,  # parent is supporting context, not scored
                        "source": "parent",
                    }
                    expansion_stats["parent"] += 1

        # Expand siblings
        if expand_siblings:
            siblings_map = _expand_siblings(db, leaf_ids, radius=sibling_radius)
            for leaf_id, sib_list in siblings_map.items():
                for sib in sib_list:
                    if sib["chunk_id"] not in expanded:
                        expanded[sib["chunk_id"]] = {
                            **sib,
                            "score": 0,
                            "source": "sibling",
                        }
                        expansion_stats["sibling"] += 1

    finally:
        db.close()

    # Step 3: assemble context — order by doc then chunk_index
    expanded_list = list(expanded.values())
    expanded_list.sort(key=lambda c: (c.get("doc_id", ""), c.get("chunk_index", 0)))

    context_parts = []
    total_tokens = 0
    MAX_CONTEXT_TOKENS = 8000

    for c in expanded_list:
        prefix = f"[{c.get('title', '')}]"
        if c.get("section_path"):
            prefix += f" § {c.get('section_path')}"
        block = f"{prefix}\n\n{c.get('content', '')}"
        block_tokens = c.get("token_count", 0) or (len(block) // 2)

        if total_tokens + block_tokens > MAX_CONTEXT_TOKENS:
            # Truncate: include partial
            remaining = MAX_CONTEXT_TOKENS - total_tokens
            if remaining > 100:
                context_parts.append(block[: remaining * 3])  # rough char estimate
            break

        context_parts.append(block)
        total_tokens += block_tokens

    context = "\n\n---\n\n".join(context_parts)

    return {
        "hits": leaf_hits,
        "expanded": expanded_list,
        "context": context,
        "stats": {
            "hits": len(leaf_hits),
            "total_expanded": len(expanded),
            **expansion_stats,
            **rerank_stats,
            "context_tokens": total_tokens,
        },
    }
