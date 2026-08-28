#!/usr/bin/env python3
"""Run a dense-only A/B evaluation on the six local RAG samples.

The input corpus is generated locally and copied to /tmp on the server.  This
script deliberately does not touch MySQL or pgvector; it only loads the two
embedding models, ranks the temporary corpus, and writes a JSON report.
"""

from __future__ import annotations

import glob
import json
import os
import sys
import time
from pathlib import Path

import numpy as np


def normalize(values: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(values, axis=1, keepdims=True)
    return values / np.maximum(norms, 1e-12)


def encode_small(texts: list[str]) -> tuple[np.ndarray, float]:
    from sentence_transformers import SentenceTransformer

    snapshots = glob.glob(
        str(Path.home() / ".cache/huggingface/hub/models--BAAI--bge-small-zh-v1.5/snapshots/*")
    )
    if not snapshots:
        raise RuntimeError("bge-small-zh-v1.5 is not available in the HF cache")
    model_path = snapshots[0]
    print(f"[small] loading {model_path}", flush=True)
    model = SentenceTransformer(model_path, device="cpu")
    started = time.perf_counter()
    values = model.encode(
        texts,
        batch_size=16,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    elapsed = time.perf_counter() - started
    return np.asarray(values, dtype=np.float32), elapsed


def encode_m3(texts: list[str]) -> tuple[np.ndarray, float]:
    from FlagEmbedding import BGEM3FlagModel

    model_path = os.getenv(
        "KB_BGE_M3_MODEL",
        str(Path.cwd() / "local_models/BAAI/bge-m3"),
    )
    print(f"[m3] loading {model_path}", flush=True)
    model = BGEM3FlagModel(model_path, use_fp16=False, device="cpu")
    started = time.perf_counter()
    output = model.encode(
        texts,
        batch_size=8,
        return_dense=True,
        return_sparse=False,
    )
    elapsed = time.perf_counter() - started
    return normalize(np.asarray(output["dense_vecs"], dtype=np.float32)), elapsed


def evaluate(
    variant: str,
    corpus: list[dict],
    queries: list[dict],
    encode,
) -> dict:
    corpus_texts = [row["content"] for row in corpus]
    query_texts = [row["query"] for row in queries]
    print(f"[{variant}] encoding {len(corpus_texts)} chunks", flush=True)
    corpus_vectors, corpus_seconds = encode(corpus_texts)
    print(f"[{variant}] encoding {len(query_texts)} queries", flush=True)
    query_vectors, query_seconds = encode(query_texts)
    scores = query_vectors @ corpus_vectors.T

    rows = []
    hit_counts = {1: 0, 3: 0, 5: 0}
    reciprocal_ranks = []
    for index, query in enumerate(queries):
        order = np.argsort(-scores[index])[:5]
        ranked = [corpus[int(position)] for position in order]
        ranked_slugs = [row["slug"] for row in ranked]
        gold = query["gold_slug"]
        rank = next(
            (position + 1 for position, slug in enumerate(ranked_slugs) if slug == gold),
            None,
        )
        for cutoff in hit_counts:
            hit_counts[cutoff] += int(gold in ranked_slugs[:cutoff])
        reciprocal_ranks.append(1.0 / rank if rank else 0.0)
        rows.append(
            {
                "id": query["id"],
                "kind": query["kind"],
                "query": query["query"],
                "gold_slug": gold,
                "gold_rank_at_5": rank,
                "top5": [
                    {
                        "slug": row["slug"],
                        "chunk_index": row["chunk_index"],
                        "token_count": row["token_count"],
                        "score": round(float(scores[index, int(position)]), 6),
                    }
                    for position, row in zip(order, ranked)
                ],
            }
        )

    count = len(queries)
    return {
        "metrics": {
            "query_count": count,
            "hit_at_1": round(hit_counts[1] / count, 4),
            "hit_at_3": round(hit_counts[3] / count, 4),
            "hit_at_5": round(hit_counts[5] / count, 4),
            "mrr": round(sum(reciprocal_ranks) / count, 4),
            "corpus_chunks": len(corpus),
            "corpus_encode_seconds": round(corpus_seconds, 2),
            "query_encode_seconds": round(query_seconds, 2),
        },
        "queries": rows,
    }


def main() -> None:
    input_path = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/rag_v3_sample_ab_corpus.json")
    output_path = Path(sys.argv[2] if len(sys.argv) > 2 else "/tmp/rag_v3_sample_ab_result.json")
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    report = {
        "scope": "six local Markdown samples; dense-only; no database writes",
        "summary": payload["summary"],
        "legacy": evaluate("legacy", payload["corpora"]["legacy"], payload["queries"], encode_small),
        "single_m3": evaluate(
            "single_m3", payload["corpora"]["single_m3"], payload["queries"], encode_m3
        ),
    }
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key]["metrics"] for key in ("legacy", "single_m3")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
