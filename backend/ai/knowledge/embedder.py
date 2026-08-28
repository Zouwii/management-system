"""Embedding pipeline: SentenceTransformer model + pgvector storage."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

from base.db.engine import KbSessionLocal, PgVectorSessionLocal

logger = logging.getLogger(__name__)

_MODEL_NAME = "BAAI/bge-small-zh-v1.5"
_SMALL_VECTOR_TABLE = "chunk_vectors"
_M3_VECTOR_TABLE = "chunk_vectors_bgem3"
_ALLOWED_VECTOR_TABLES = {_SMALL_VECTOR_TABLE, _M3_VECTOR_TABLE}
_model = None
_model_loading = False  # True while model is being loaded (prevents re-entry)


def embedding_config() -> dict:
    """Return the configured embedding backend and its vector table."""
    selected = (os.getenv("KB_EMBEDDING_MODEL") or "bge-small").strip().lower()
    if selected in {"m3", "bge-m3", "bgem3"}:
        table = os.getenv("KB_EMBEDDING_VECTOR_TABLE") or _M3_VECTOR_TABLE
        model = "m3"
        dimension = 1024
    else:
        table = os.getenv("KB_EMBEDDING_VECTOR_TABLE") or _SMALL_VECTOR_TABLE
        model = "small"
        dimension = 512
    if table not in _ALLOWED_VECTOR_TABLES:
        raise ValueError(f"unsupported embedding vector table: {table}")
    expected_table = _M3_VECTOR_TABLE if model == "m3" else _SMALL_VECTOR_TABLE
    if table != expected_table:
        raise ValueError(
            f"embedding model {model} must use {expected_table}, got {table}"
        )
    return {"model": model, "table": table, "dimension": dimension}


def embedding_vector_table() -> str:
    return embedding_config()["table"]


def is_model_ready() -> bool:
    """Return True if the embedding model is loaded and ready to use."""
    return _model is not None


def delete_vectors(chunk_ids, vector_table: Optional[str] = None) -> int:
    """Delete vectors for chunks that are about to be rebuilt."""
    ids = [int(chunk_id) for chunk_id in chunk_ids]
    if not ids:
        return 0

    from sqlalchemy import text

    table = vector_table or embedding_vector_table()
    if table not in _ALLOWED_VECTOR_TABLES:
        raise ValueError(f"unsupported embedding vector table: {table}")
    deleted = 0
    pg = PgVectorSessionLocal()
    try:
        for start in range(0, len(ids), 500):
            batch = ids[start:start + 500]
            placeholders = ",".join(f":id_{i}" for i in range(len(batch)))
            result = pg.execute(
                text(f"DELETE FROM {table} WHERE chunk_id IN ({placeholders})"),
                {f"id_{i}": chunk_id for i, chunk_id in enumerate(batch)},
            )
            deleted += max(0, int(result.rowcount or 0))
        pg.commit()
        return deleted
    except Exception:
        pg.rollback()
        raise
    finally:
        pg.close()


def _load_model():
    """Eagerly load the embedding model. Call once at process start."""
    global _model, _model_loading
    if _model is not None or _model_loading:
        return
    _model_loading = True
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    import torch
    torch.set_num_threads(1)
    try:
        if embedding_config()["model"] == "m3":
            from FlagEmbedding import BGEM3FlagModel

            default_path = (
                Path(__file__).resolve().parents[2]
                / "local_models" / "BAAI" / "bge-m3"
            )
            model_path = os.getenv("KB_BGE_M3_MODEL") or str(default_path)
            _model = BGEM3FlagModel(
                model_path,
                use_fp16=False,
                device="cpu",
            )
        else:
            from sentence_transformers import SentenceTransformer

            _model = SentenceTransformer(
                _MODEL_NAME,
                local_files_only=True,
                device="cpu",
            )
    finally:
        _model_loading = False


def _get_model():
    if _model is None:
        _load_model()
    return _model


def encode_texts(texts: list[str], *, batch_size: int = 32):
    """Encode texts using the configured model and return dense vectors."""
    model = _get_model()
    if embedding_config()["model"] == "m3":
        output = model.encode(
            texts,
            batch_size=batch_size,
            return_dense=True,
            return_sparse=False,
        )
        return output["dense_vecs"]
    return model.encode(
        texts,
        batch_size=batch_size,
        normalize_embeddings=True,
        show_progress_bar=False,
    )


def embed_chunks(
    workspace_id: Optional[str] = None,
    limit: int = 0,
    batch_size: int = 32,
    depth: Optional[int] = 1,
) -> dict:
    """Embed kb_chunks and store vectors in pgvector chunk_vectors.

    Skips chunks that already have a vector entry.
    Embeds leaf chunks (depth=1) by default. Pass depth=None only for an
    explicit all-depth maintenance operation.
    Returns counts: {chunk_total, embedded, skipped, errors}.
    """
    table = embedding_vector_table()
    _get_model()

    kb = KbSessionLocal()
    pg = PgVectorSessionLocal()
    stats = {"chunk_total": 0, "embedded": 0, "skipped": 0, "errors": 0}

    try:
        from sqlalchemy import text

        # Build WHERE clauses
        where_clauses = []
        params: dict = {}
        if workspace_id:
            where_clauses.append("d.workspace_id = :ws_id")
            params["ws_id"] = workspace_id
        if depth is not None:
            where_clauses.append("c.depth = :depth")
            params["depth"] = depth
        where_str = (" AND " + " AND ".join(where_clauses)) if where_clauses else ""

        join_clause = "JOIN kb_documents d ON c.doc_id = d.node_id" if workspace_id else ""

        count_sql = text(f"SELECT COUNT(*) FROM kb_chunks c {join_clause} WHERE 1=1 {where_str}")
        total = kb.execute(count_sql, params).scalar()
        stats["chunk_total"] = total

        offset = 0
        while True:
            if limit and offset >= limit:
                break
            batch_limit = min(batch_size, limit - offset) if limit else batch_size

            batch_params = {**params, "limit": batch_limit, "offset": offset}
            sel = text(
                f"SELECT c.id, c.content FROM kb_chunks c {join_clause} "
                f"WHERE 1=1 {where_str} "
                f"ORDER BY c.id LIMIT :limit OFFSET :offset"
            )
            rows = kb.execute(sel, batch_params).fetchall()

            if not rows:
                break

            chunk_ids = [r[0] for r in rows]
            contents = [r[1] or "" for r in rows]

            # check which already have vectors
            placeholders = ",".join([f":id_{i}" for i in range(len(chunk_ids))])
            existing = pg.execute(
                text(
                    f"SELECT chunk_id FROM {table} WHERE chunk_id IN ({placeholders})"
                ),
                {f"id_{i}": cid for i, cid in enumerate(chunk_ids)},
            ).fetchall()
            existing_ids = {r[0] for r in existing}

            new_rows = [
                (cid, content)
                for cid, content in zip(chunk_ids, contents)
                if cid not in existing_ids
            ]
            stats["skipped"] += len(chunk_ids) - len(new_rows)

            if new_rows:
                new_ids, new_contents = zip(*new_rows)
                try:
                    embeddings = encode_texts(list(new_contents), batch_size=batch_size)
                    for cid, emb in zip(new_ids, embeddings):
                        pg.execute(
                            text(
                                f"INSERT INTO {table} (chunk_id, embedding) "
                                "VALUES (:cid, :emb)"
                            ),
                            {"cid": cid, "emb": emb.tolist()},
                        )
                    pg.commit()
                    stats["embedded"] += len(new_ids)
                except Exception:
                    logger.exception("embed batch failed")
                    stats["errors"] += len(new_ids)

            offset += batch_size

        return stats
    finally:
        kb.close()
        pg.close()
