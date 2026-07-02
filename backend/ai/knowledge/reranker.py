"""Cross-Encoder 重排模块。

默认使用 bge-reranker-base（280MB），通过环境变量 RERANKER_MODEL 可切换：
  RERANKER_MODEL=base    → bge-reranker-base (280MB, 快)
  RERANKER_MODEL=v2-m3   → bge-reranker-v2-m3 (2.2GB, 更准)
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent

logger = logging.getLogger(__name__)

_reranker = None
_reranker_model: str = ""


def _get_model_dir(model: str) -> Path:
    dirs = {
        "base": BACKEND_ROOT / "local_models" / "BAAI" / "bge-reranker-base",
        "v2-m3": BACKEND_ROOT / "local_models" / "BAAI" / "bge-reranker-v2-m3",
    }
    return dirs[model]


def get_reranker(model: str | None = None):
    """懒加载 reranker，全局单例。

    Args:
        model: "base" 或 "v2-m3"，默认读环境变量 RERANKER_MODEL，兜底 "base"
    """
    global _reranker, _reranker_model

    if model is None:
        model = os.environ.get("RERANKER_MODEL", "base")

    if _reranker is not None and _reranker_model == model:
        return _reranker

    from FlagEmbedding import FlagReranker

    model_dir = _get_model_dir(model)
    logger.info("Loading reranker [%s] from %s ...", model, model_dir)
    _reranker = FlagReranker(str(model_dir), use_fp16=False, device="cpu")
    _reranker_model = model
    logger.info("Reranker [%s] loaded", model)
    return _reranker


def rerank(
    query: str,
    candidates: list[dict],
    max_chars: int = 600,
    model: str | None = None,
) -> list[dict]:
    """对候选列表重排，返回按相关性降序的结果。

    Args:
        query: 用户查询
        candidates: 候选 chunk 列表，每条需含 "content" 字段
        max_chars: chunk 截取长度（字符数）
        model: 模型名，默认 "base"

    Returns:
        附带 _rerank_score 的排序后列表
    """
    if len(candidates) <= 1:
        return candidates

    rr = get_reranker(model)
    pairs = [[query, (c.get("content") or "")[:max_chars]] for c in candidates]
    scores = rr.compute_score(pairs, normalize=True)

    if not isinstance(scores, list):
        scores = [scores]

    for c, s in zip(candidates, scores):
        c["_rerank_score"] = float(s)

    ranked = sorted(candidates, key=lambda x: x.get("_rerank_score", 0), reverse=True)
    return ranked
