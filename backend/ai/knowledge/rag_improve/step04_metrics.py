"""检索评估指标：Recall@K, MRR, nDCG@K。"""
from __future__ import annotations
import math


def recall_at_k(predicted: list[int], relevant: list[int], k: int = 5) -> float:
    """Recall@K = |top-K 命中正确答案数| / |正确答案总数|。

    衡量"该找的找到没有"。
    """
    if not relevant:
        return 1.0
    top_k = set(predicted[:k])
    hits = top_k & set(relevant)
    return len(hits) / len(relevant)


def mrr(predicted: list[int], relevant: list[int]) -> float:
    """MRR (Mean Reciprocal Rank) = 首个正确结果排名的倒数。

    衡量"正确答案排得有多靠前"。
    """
    if not relevant:
        return 1.0
    rset = set(relevant)
    for i, pid in enumerate(predicted, start=1):
        if pid in rset:
            return 1.0 / i
    return 0.0


def ndcg_at_k(predicted: list[int], relevant: list[int], k: int = 5) -> float:
    """nDCG@K：归一化折损累积增益。

    同时考虑"命中多少"和"命中位置"，排名靠前权重高。
    使用二值相关性（1/0）。
    """
    if not relevant:
        return 1.0
    rset = set(relevant)
    dcg = 0.0
    for i, pid in enumerate(predicted[:k], start=1):
        rel = 1.0 if pid in rset else 0.0
        dcg += rel / math.log2(i + 1)

    # IDCG: 理想排列——所有相关 chunk 排最前面
    ideal_hits = min(len(relevant), k)
    idcg = 0.0
    for i in range(1, ideal_hits + 1):
        idcg += 1.0 / math.log2(i + 1)

    return dcg / idcg if idcg > 0 else 0.0
