"""标注助手：逐条显示当前基线检索（Group A）的候选chunk，交互式标记 relevant_chunk_ids。

用法：
  python -m ai.knowledge.rag_improve.annotate     # 从头开始标注
  python -m ai.knowledge.rag_improve.annotate --resume  # 跳过已有标注的
"""
from __future__ import annotations
import json
import sys
import os
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

from ai.knowledge.retriever import search_hybrid

TEST_QUERIES_PATH = Path(__file__).parent / "test_queries.json"


def load_queries():
    with open(TEST_QUERIES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_queries(queries):
    with open(TEST_QUERIES_PATH, "w", encoding="utf-8") as f:
        json.dump(queries, f, ensure_ascii=False, indent=2)


def run_baseline(query: str, top_k: int = 20):
    """用 Group A (基线) 检索，返回候选 chunk 列表。"""
    results = search_hybrid(query, top_k=top_k)
    return results


def annotate_one(q, resume: bool = False):
    """标注单条查询。"""
    if resume and q.get("relevant_chunk_ids") and len(q["relevant_chunk_ids"]) > 0:
        return None  # 跳过

    print(f"\n{'='*60}")
    print(f"问题 #{q['id']} [{q['type']} | {q['difficulty']}]")
    print(f"查询: {q['query']}")
    print(f"预期来源: {', '.join(q.get('source_docs', []))}")
    print(f"备注: {q.get('note', '-')}")

    # 运行基线检索
    print(f"\n--- 基线检索结果 (Top-20) ---")
    candidates = run_baseline(q["query"], top_k=20)

    if not candidates:
        print("(无搜索结果)")
        return None

    for i, c in enumerate(candidates):
        print(f"\n[{i+1}] chunk_id={c['chunk_id']} | {c['title']} | score={c['score']:.4f}")
        print(f"    {c['content'][:300]}")
        if len(c['content']) > 300:
            print("    ...")

    print(f"\n--- 请标注正确答案 ---")
    print("输入格式:")
    print("  1,3,5    → 选中第1、3、5条作为正确答案")
    print("  s         → 跳过此问题（不标注）")
    print("  d 1       → 查看第1条的完整内容")
    print("  q         → 退出标注")

    selected = set(q.get("relevant_chunk_ids", []))
    if selected:
        print(f"\n已有标注: {sorted(selected)}")

    while True:
        try:
            cmd = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n退出标注")
            return "quit"

        if not cmd:
            continue
        if cmd.lower() == "q":
            return "quit"
        if cmd.lower() == "s":
            return None  # 跳过，不修改

        if cmd.lower().startswith("d "):
            try:
                idx = int(cmd.split()[1]) - 1
                if 0 <= idx < len(candidates):
                    print(f"\n=== chunk_id={candidates[idx]['chunk_id']} 完整内容 ===")
                    print(candidates[idx]['content'])
                else:
                    print(f"索引超出范围 (1-{len(candidates)})")
            except (ValueError, IndexError):
                print("格式: d <序号>")
            continue

        # 解析索引
        try:
            idxs = [int(x.strip()) for x in cmd.split(",") if x.strip()]
            selected = set()
            for idx in idxs:
                if 1 <= idx <= len(candidates):
                    selected.add(candidates[idx - 1]["chunk_id"])
                else:
                    print(f"索引 {idx} 超出范围 (1-{len(candidates)})，已忽略")
            q["relevant_chunk_ids"] = sorted(selected)
            print(f"已标注: {sorted(selected)}")
            return "updated"
        except ValueError:
            print("无效输入，请重试")


def main():
    resume = "--resume" in sys.argv
    queries = load_queries()

    annotated_count = sum(
        1 for q in queries if q.get("relevant_chunk_ids") and len(q["relevant_chunk_ids"]) > 0
    )
    total = len(queries)
    print(f"已标注: {annotated_count}/{total}")

    for q in queries:
        result = annotate_one(q, resume=resume)
        if result == "quit":
            break
        if result == "updated":
            save_queries(queries)
            print("(已保存)")

    # 最终统计
    queries = load_queries()
    done = sum(
        1 for q in queries if q.get("relevant_chunk_ids") and len(q["relevant_chunk_ids"]) > 0
    )
    print(f"\n标注完成: {done}/{total}")
    if done < total:
        undone = [q["id"] for q in queries if not q.get("relevant_chunk_ids") or len(q["relevant_chunk_ids"]) == 0]
        print(f"未标注的问题 ID: {undone}")


if __name__ == "__main__":
    main()
