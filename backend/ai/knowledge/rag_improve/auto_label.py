"""自动预标注：根据 source_docs 匹配检索结果中的文档标题，自动填充 relevant_chunk_ids。

用法: python -m ai.knowledge.rag_improve.auto_label
"""
from __future__ import annotations
import json, sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

from ai.knowledge.retriever import search_hybrid

TEST_QUERIES_PATH = Path(__file__).parent / "test_queries.json"


def matches_source(chunk_title: str, source_docs: list[str]) -> bool:
    """检查 chunk 所属文档是否在预期来源列表中。"""
    for doc in source_docs:
        # 支持精确匹配和部分匹配（处理带特殊字符的文档名）
        if doc in chunk_title or chunk_title in doc:
            return True
    return False


def auto_label():
    queries = json.loads(TEST_QUERIES_PATH.read_text(encoding="utf-8"))
    total_labeled = 0

    for q in queries:
        if q.get("relevant_chunk_ids") and len(q["relevant_chunk_ids"]) > 0:
            continue  # 已标注，跳过

        source_docs = q.get("source_docs", [])
        if not source_docs:
            print(f"  #{q['id']:2d} 无 source_docs，跳过")
            continue

        # 用基线检索
        results = search_hybrid(q["query"], top_k=30)

        # 匹配 source_docs
        matched = []
        for r in results:
            if matches_source(r["title"], source_docs):
                matched.append(r["chunk_id"])

        if matched:
            q["relevant_chunk_ids"] = sorted(set(matched))
            total_labeled += 1
            print(f"  #{q['id']:2d} ✓ 自动标注 {len(matched)} 个 chunk ← {source_docs[0]}")
        else:
            print(f"  #{q['id']:2d} ✗ 未匹配到 chunk (来源: {source_docs})")

    # 保存
    TEST_QUERIES_PATH.write_text(json.dumps(queries, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n自动标注完成: {total_labeled}/{len(queries)} 条")


if __name__ == "__main__":
    auto_label()
