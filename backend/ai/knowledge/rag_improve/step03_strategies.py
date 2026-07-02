"""A vs B 检索策略定义。

A（基线）: Hybrid RRF → top-k
B（实验）: Hybrid RRF + 纯向量双路召回 → 合并去重 → Cross-Encoder 重排 → top-k
"""
from __future__ import annotations
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

from ai.knowledge.retriever import search_hybrid, search_vector

_reranker = None


_reranker = None
_reranker_model = ""


def _get_reranker(model: str = "base"):
    """懒加载 reranker 模型。

    Args:
        model: "base" (bge-reranker-base, 280MB) 或 "v2-m3" (2.2GB)
    """
    global _reranker, _reranker_model
    if _reranker is not None and _reranker_model == model:
        return _reranker

    from FlagEmbedding import FlagReranker

    model_dirs = {
        "base": BACKEND_ROOT / "local_models" / "BAAI" / "bge-reranker-base",
        "v2-m3": BACKEND_ROOT / "local_models" / "BAAI" / "bge-reranker-v2-m3",
    }
    model_dir = model_dirs[model]

    # P1000 GPU 推理比 CPU 慢，统一用 CPU
    fp16, dev = False, "cpu"

    print(f"[reranker:{model}] loading from {model_dir} ({dev}) ...", end=" ", flush=True)
    _reranker = FlagReranker(str(model_dir), use_fp16=fp16, device=dev)
    _reranker_model = model
    print("done")
    return _reranker


def strategy_a(query: str, k: int = 5) -> list[dict]:
    """基线策略：Hybrid RRF 检索，无重排。"""
    results = search_hybrid(query, top_k=k)
    return results


def strategy_b(query: str, k: int = 5, recall_k: int = 20, max_chars: int = 600,
               reranker_model: str = "base") -> list[dict]:
    """实验策略（v3）：Hybrid RRF 单路召回 → Cross-Encoder 精排。

    1. Hybrid RRF 召回 top-{recall_k}（v2 双路召回已证伪，噪音反噬精度）
    2. chunk 内容截取前 {max_chars} 字符
    3. bge-reranker-{reranker_model} 对每个 (query, chunk) 对打分
    4. 按 rerank 分数降序排列，取 top-k
    """
    candidates = search_hybrid(query, top_k=recall_k)

    if not candidates:
        return []

    reranker = _get_reranker(reranker_model)
    # 截取前 max_chars，加速 tokenize
    pairs = [[query, (c["content"] or "")[:max_chars]] for c in candidates]
    scores = reranker.compute_score(pairs, normalize=True)

    if not isinstance(scores, list):
        scores = [scores]

    for c, s in zip(candidates, scores):
        c["_rerank_score"] = float(s)

    ranked = sorted(candidates, key=lambda x: x["_rerank_score"], reverse=True)
    return ranked[:k]
