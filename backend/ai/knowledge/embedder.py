"""Embedding pipeline: SentenceTransformer model + pgvector storage."""

from __future__ import annotations

import logging
import os
from typing import Optional

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

from base.db.engine import PgVectorSessionLocal, SessionLocal

logger = logging.getLogger(__name__)

_MODEL_NAME = "BAAI/bge-small-zh-v1.5"
_model = None


def _load_model():
    """Eagerly load the embedding model. Call once at process start."""
    global _model
    if _model is not None:
        return
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    import torch
    torch.set_num_threads(1)
    from sentence_transformers import SentenceTransformer
    _model = SentenceTransformer(_MODEL_NAME, local_files_only=True)


def _get_model():
    if _model is None:
        _load_model()
    return _model


def embed_chunks(
    workspace_id: Optional[str] = None,
    limit: int = 0,
    batch_size: int = 32,
) -> dict:
    """Embed kb_chunks and store vectors in pgvector chunk_vectors.

    Skips chunks that already have a vector entry.
    Returns counts: {chunk_total, embedded, skipped, errors}.
    """
    model = _get_model()
    dim = model.get_embedding_dimension()

    mysql = SessionLocal()
    pg = PgVectorSessionLocal()
    stats = {"chunk_total": 0, "embedded": 0, "skipped": 0, "errors": 0}

    try:
        # which chunks need embedding
        from sqlalchemy import text

        if workspace_id:
            count_sql = text(
                "SELECT COUNT(*) FROM kb_chunks c "
                "JOIN kb_documents d ON c.doc_id = d.doc_id "
                "WHERE d.workspace_id = :ws_id"
            )
            total = mysql.execute(count_sql, {"ws_id": workspace_id}).scalar()
        else:
            total = mysql.execute(text("SELECT COUNT(*) FROM kb_chunks")).scalar()
        stats["chunk_total"] = total

        offset = 0
        while True:
            if limit and offset >= limit:
                break
            batch_limit = min(batch_size, limit - offset) if limit else batch_size

            if workspace_id:
                sel = text(
                    "SELECT c.id, c.content FROM kb_chunks c "
                    "JOIN kb_documents d ON c.doc_id = d.doc_id "
                    "WHERE d.workspace_id = :ws_id "
                    "ORDER BY c.id LIMIT :limit OFFSET :offset"
                )
                rows = mysql.execute(
                    sel, {"ws_id": workspace_id, "limit": batch_limit, "offset": offset}
                ).fetchall()
            else:
                sel = text(
                    "SELECT id, content FROM kb_chunks "
                    "ORDER BY id LIMIT :limit OFFSET :offset"
                )
                rows = mysql.execute(
                    sel, {"limit": batch_limit, "offset": offset}
                ).fetchall()

            if not rows:
                break

            chunk_ids = [r[0] for r in rows]
            contents = [r[1] or "" for r in rows]

            # check which already have vectors
            placeholders = ",".join([f":id_{i}" for i in range(len(chunk_ids))])
            existing = pg.execute(
                text(
                    f"SELECT chunk_id FROM chunk_vectors WHERE chunk_id IN ({placeholders})"
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
                    embeddings = model.encode(
                        list(new_contents),
                        normalize_embeddings=True,
                        show_progress_bar=False,
                    )
                    for cid, emb in zip(new_ids, embeddings):
                        pg.execute(
                            text(
                                "INSERT INTO chunk_vectors (chunk_id, embedding) "
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
        mysql.close()
        pg.close()
