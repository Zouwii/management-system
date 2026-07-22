"""批量编码存量 chunk → 新向量表 (bge-m3 + bge-large)

用法:
  python -m ai.knowledge.rag_improve.step06_encode_vectors        # 两个模型都编码
  python -m ai.knowledge.rag_improve.step06_encode_vectors --large  # 只编码 bge-large
  python -m ai.knowledge.rag_improve.step06_encode_vectors --m3     # 只编码 bge-m3

模型需通过 modelscope 预先下载到 local_models/BAAI/：
  snapshot_download('BAAI/bge-large-zh-v1.5', cache_dir='./local_models')
  snapshot_download('BAAI/bge-m3', cache_dir='./local_models')
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path
from typing import Optional

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")  # 强制 CPU，避免 CUDA 驱动故障卡死

BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

import torch
from base.db.engine import KbSessionLocal, PgVectorSessionLocal
from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

LOCAL_MODELS = BACKEND_ROOT / "local_models" / "BAAI"

MODEL_CFG = {
    "large": {
        "name": "bge-large-zh-v1___5",   # modelscope 命名，注意下划线
        "table": "chunk_vectors_large",
        "dim": 1024,
        "library": "sentence_transformers",
    },
    "m3": {
        "name": "bge-m3",
        "table": "chunk_vectors_bgem3",
        "dim": 1024,
        "library": "flagembedding",
    },
}


def get_chunks(limit=None):
    db = KbSessionLocal()
    try:
        if limit:
            rows = db.execute(
                text("SELECT id, content FROM kb_chunks ORDER BY id LIMIT :limit"),
                {"limit": limit},
            ).fetchall()
        else:
            rows = db.execute(
                text("SELECT id, content FROM kb_chunks ORDER BY id")
            ).fetchall()
        logger.info("Total kb_chunks: %d", len(rows))
        return [(r[0], r[1] or "") for r in rows]
    finally:
        db.close()


def get_encoded_ids(pg, table):
    try:
        r = pg.execute(text(f"SELECT chunk_id FROM {table}")).fetchall()
        return {row[0] for row in r}
    except Exception:
        return {}


def encode_with_st(model_name, chunks, batch_size, device="cuda"):
    from sentence_transformers import SentenceTransformer
    logger.info("Loading %s on %s ...", model_name, device)
    model = SentenceTransformer(model_name, device=device)
    if device == "cuda":
        model.half()

    results = []
    total = len(chunks)
    for i in range(0, total, batch_size):
        batch = chunks[i:i + batch_size]
        ids = [c[0] for c in batch]
        texts = [c[1] for c in batch]
        embeddings = model.encode(
            texts, normalize_embeddings=True, show_progress_bar=False,
            batch_size=batch_size,
        )
        for cid, emb in zip(ids, embeddings):
            results.append((cid, emb.tolist()))
        if (i + batch_size) % 500 == 0 or i + batch_size >= total:
            logger.info("  bge-large: %d/%d (%.0f%%)", i + len(batch), total,
                        100 * (i + len(batch)) / total)
    return results


def encode_with_flagembedding(model_name, chunks, batch_size, device="cuda"):
    from FlagEmbedding import BGEM3FlagModel
    logger.info("Loading %s on %s ...", model_name, device)
    model = BGEM3FlagModel(model_name, use_fp16=(device == "cuda"), device=device)

    results = []
    total = len(chunks)
    for i in range(0, total, batch_size):
        batch = chunks[i:i + batch_size]
        ids = [c[0] for c in batch]
        texts = [c[1] for c in batch]
        out = model.encode(texts, return_dense=True, return_sparse=False)
        dense = out["dense_vecs"]
        for cid, emb in zip(ids, dense):
            results.append((cid, emb.tolist()))
        if (i + batch_size) % 500 == 0 or i + batch_size >= total:
            logger.info("  bge-m3: %d/%d (%.0f%%)", i + len(batch), total,
                        100 * (i + len(batch)) / total)
    return results


def insert_vectors(pg, table, vectors):
    count = 0
    for cid, emb in vectors:
        emb_str = "[" + ",".join(str(x) for x in emb) + "]"
        try:
            pg.execute(
                text(f"INSERT INTO {table} (chunk_id, embedding) VALUES (:cid, :emb) "
                     f"ON CONFLICT (chunk_id) DO UPDATE SET embedding = EXCLUDED.embedding"),
                {"cid": cid, "emb": emb_str},
            )
            pg.commit()
            count += 1
        except Exception:
            pg.rollback()
            logger.exception("Failed to insert chunk_id=%d", cid)
    return count


def run_model(model_key, batch_size=4, device="cuda", limit=None):
    cfg = MODEL_CFG[model_key]
    table = cfg["table"]
    model_path = str(LOCAL_MODELS / cfg["name"])

    logger.info("=" * 60)
    logger.info("Encoding: %s -> %s (batch=%d, device=%s)", cfg["name"], table, batch_size, device)

    chunks = get_chunks(limit=limit)
    if not chunks:
        return

    pg = PgVectorSessionLocal()
    try:
        existing = get_encoded_ids(pg, table)
        new_chunks = [(cid, txt) for cid, txt in chunks if cid not in existing]
        logger.info("Already encoded: %d, to encode: %d", len(existing), len(new_chunks))

        if not new_chunks:
            logger.info("All chunks already encoded, skipping.")
            return

        t0 = time.time()

        if cfg["library"] == "sentence_transformers":
            vectors = encode_with_st(model_path, new_chunks, batch_size, device)
        else:
            vectors = encode_with_flagembedding(model_path, new_chunks, batch_size, device)

        inserted = insert_vectors(pg, table, vectors)
        elapsed = time.time() - t0
        logger.info("Done: %d vectors in %.1fs (%.1f chunks/s)", inserted, elapsed, inserted / elapsed)
    finally:
        pg.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--large", action="store_true")
    parser.add_argument("--m3", action="store_true")
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--cpu", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    device = "cpu" if args.cpu else ("cuda" if torch.cuda.is_available() else "cpu")
    logger.info("Device: %s, GPU: %s", device,
                 torch.cuda.get_device_name(0) if device == "cuda" else "N/A")
    if device == "cuda":
        logger.info("VRAM: %.1f GB", torch.cuda.get_device_properties(0).total_memory / 1e9)

    limit = args.limit if args.limit > 0 else None
    run_both = not args.large and not args.m3

    if run_both or args.large:
        run_model("large", batch_size=args.batch_size, device=device, limit=limit)

    if run_both or args.m3:
        run_model("m3", batch_size=args.batch_size, device=device, limit=limit)


if __name__ == "__main__":
    main()
