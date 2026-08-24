#!/usr/bin/env python3
"""Evaluate the v2 query set with production Hybrid RRF retrieval, no reranking."""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path


if backend_root_env := os.environ.get("RAG_PROJECT_BACKEND"):
    BACKEND_ROOT = Path(backend_root_env)
else:
    BACKEND_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(BACKEND_ROOT))

from ai.knowledge.embedder import _load_model, is_model_ready  # noqa: E402
from ai.knowledge.rag_improve.step04_metrics import (  # noqa: E402
    mrr,
    ndcg_at_k,
    recall_at_k,
)
from ai.knowledge import retriever  # noqa: E402


def percentile(values: list[float], percentile_value: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile_value
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def aggregate(rows: list[dict]) -> dict:
    if not rows:
        return {}
    latencies = [row["latency_ms"] for row in rows]
    return {
        "question_count": len(rows),
        "recall_at_5": round(statistics.fmean(row["recall_at_5"] for row in rows), 4),
        "recall_at_10": round(statistics.fmean(row["recall_at_10"] for row in rows), 4),
        "hit_at_5": round(statistics.fmean(row["hit_at_5"] for row in rows), 4),
        "hit_at_10": round(statistics.fmean(row["hit_at_10"] for row in rows), 4),
        "mrr_at_10": round(statistics.fmean(row["mrr_at_10"] for row in rows), 4),
        "ndcg_at_5": round(statistics.fmean(row["ndcg_at_5"] for row in rows), 4),
        "ndcg_at_10": round(statistics.fmean(row["ndcg_at_10"] for row in rows), 4),
        "latency_ms": {
            "mean": round(statistics.fmean(latencies), 2),
            "p50": round(percentile(latencies, 0.50), 2),
            "p95": round(percentile(latencies, 0.95), 2),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--rerank", action="store_true")
    args = parser.parse_args()

    questions = json.loads(args.input.read_text(encoding="utf-8"))

    model_started = time.perf_counter()
    _load_model()
    model_load_ms = round((time.perf_counter() - model_started) * 1000, 2)
    if not is_model_ready():
        raise RuntimeError("embedding model failed to load; refusing a keyword-only run")

    reranker_load_ms = None
    if args.rerank:
        from ai.knowledge.reranker import get_reranker, is_reranker_ready

        reranker_started = time.perf_counter()
        get_reranker()
        reranker_load_ms = round((time.perf_counter() - reranker_started) * 1000, 2)
        if not is_reranker_ready():
            raise RuntimeError("reranker failed to load; refusing an unreranked fallback run")

    original_keyword = retriever.search_chunks
    original_vector = retriever.search_vector
    route_counts: dict[str, int] = {}

    def observed_keyword(*call_args, **call_kwargs):
        values = original_keyword(*call_args, **call_kwargs)
        route_counts["keyword"] = len(values)
        return values

    def observed_vector(*call_args, **call_kwargs):
        values = original_vector(*call_args, **call_kwargs)
        route_counts["vector"] = len(values)
        return values

    retriever.search_chunks = observed_keyword
    retriever.search_vector = observed_vector

    rows = []
    for index, question in enumerate(questions, start=1):
        route_counts.clear()
        started = time.perf_counter()
        search = retriever.search_with_rerank if args.rerank else retriever.search_hybrid
        results = search(question["query"], top_k=args.top_k)
        latency_ms = round((time.perf_counter() - started) * 1000, 2)

        predicted = [int(item["chunk_id"]) for item in results]
        relevant = [int(value) for value in question["relevant_chunk_ids"]]
        hit_ids_5 = sorted(set(predicted[:5]) & set(relevant))
        hit_ids_10 = sorted(set(predicted[:10]) & set(relevant))
        row = {
            "id": question["id"],
            "type": question["type"],
            "difficulty": question["difficulty"],
            "query": question["query"],
            "gold_leaf_ids": relevant,
            "predicted_leaf_ids": predicted,
            "hit_leaf_ids_at_5": hit_ids_5,
            "hit_leaf_ids_at_10": hit_ids_10,
            "recall_at_5": recall_at_k(predicted, relevant, 5),
            "recall_at_10": recall_at_k(predicted, relevant, 10),
            "hit_at_5": int(bool(hit_ids_5)),
            "hit_at_10": int(bool(hit_ids_10)),
            "mrr_at_10": mrr(predicted[:10], relevant),
            "ndcg_at_5": ndcg_at_k(predicted, relevant, 5),
            "ndcg_at_10": ndcg_at_k(predicted, relevant, 10),
            "latency_ms": latency_ms,
            "keyword_candidates": route_counts.get("keyword", 0),
            "vector_candidates": route_counts.get("vector", 0),
            "results": [
                {
                    "rank": rank,
                    "leaf_id": int(item["chunk_id"]),
                    "title": item.get("title"),
                    "chunk_index": item.get("chunk_index"),
                    "score": item.get("score"),
                    "rerank_score": item.get("_rerank_score"),
                }
                for rank, item in enumerate(results, start=1)
            ],
        }
        rows.append(row)
        print(
            f"[{index:02d}/{len(questions)}] id={question['id']} "
            f"R@5={row['recall_at_5']:.3f} R@10={row['recall_at_10']:.3f} "
            f"kw={row['keyword_candidates']} vec={row['vector_candidates']} "
            f"{latency_ms:.0f}ms",
            flush=True,
        )

    groups: dict[str, dict[str, list[dict]]] = {
        "difficulty": defaultdict(list),
        "type": defaultdict(list),
    }
    for row in rows:
        groups["difficulty"][row["difficulty"]].append(row)
        groups["type"][row["type"]].append(row)

    payload = {
        "experiment": {
            "name": (
                "rag_v2_hybrid_rrf_with_rerank"
                if args.rerank
                else "rag_v2_hybrid_rrf_no_rerank"
            ),
            "run_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "input": str(args.input),
            "retrieval": "search_hybrid (keyword FULLTEXT + vector cosine + RRF)",
            "rerank": args.rerank,
            "reranker": "bge-reranker-base" if args.rerank else None,
            "top_k": args.top_k,
            "embedding_model_ready": is_model_ready(),
            "embedding_model_load_ms": model_load_ms,
            "reranker_load_ms": reranker_load_ms,
        },
        "summary": aggregate(rows),
        "by_difficulty": {
            name: aggregate(group_rows)
            for name, group_rows in sorted(groups["difficulty"].items())
        },
        "by_type": {
            name: aggregate(group_rows)
            for name, group_rows in sorted(groups["type"].items())
        },
        "per_question": rows,
    }
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload["summary"], ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
