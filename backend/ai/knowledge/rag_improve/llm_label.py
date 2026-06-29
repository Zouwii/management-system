"""LLM 辅助标注：Pooling 多路检索 → 候选池 → LLM 判 relevance → 写入 test_queries.json

方法：TREC 标准 Pooling 范式
  - 三路检索（FTS关键词 + 向量语义 + Hybrid混合）各取 top-15
  - 合并去重形成候选池
  - LLM (deepseek-v4-pro) 逐条标注 relevance

用法: python -m ai.knowledge.rag_improve.llm_label
"""
from __future__ import annotations
import json, requests, sys, time
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

from ai.knowledge.retriever import search_chunks, search_vector, search_hybrid

TEST_QUERIES_PATH = Path(__file__).parent / "test_queries.json"
CONFIG_PATH = BACKEND_ROOT / "ai" / "config.json"


def load_config():
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def call_llm(messages: list[dict], model: str = "deepseek-v4-pro") -> str:
    """调用 one-api，返回 LLM 文本响应。"""
    cfg = load_config()
    url = f"{cfg['base_url'].rstrip('/')}/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {cfg['api_key']}",
    }
    resp = requests.post(
        url,
        headers=headers,
        json={
            "model": model,
            "messages": messages,
            "temperature": 0.0,
            "max_tokens": 2048,
        },
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


def pool_candidates(query: str, top_k: int = 15) -> list[dict]:
    """TREC 标准 Pooling：三路检索合并去重，形成候选池。

    三路：
      - FTS 关键词检索（MySQL FULLTEXT）
      - 向量语义检索（pgvector cosine）
      - Hybrid 混合检索（RRF 融合）

    返回去重后的 chunk 列表，约 30~40 条。
    """
    seen: set[int] = set()
    pooled: list[dict] = []

    # 三路各取 top-k
    sources = [
        ("FTS", search_chunks(query, top_k=top_k)),
        ("向量", search_vector(query, top_k=top_k)),
        ("Hybrid", search_hybrid(query, top_k=top_k)),
    ]

    for label, results in sources:
        for r in results:
            cid = r["chunk_id"]
            if cid not in seen:
                seen.add(cid)
                r["_source"] = label
                pooled.append(r)

    return pooled


def build_prompt(query: str, chunks: list[dict]) -> list[dict]:
    """构造标注 prompt。"""
    lines = []
    for i, c in enumerate(chunks):
        content = c["content"][:800]  # 加大到 800 字符
        lines.append(f"片段 {i+1} (chunk_id={c['chunk_id']}, 来源={c.get('_source','?')}):")
        lines.append(content)
        lines.append("---")

    system = (
        "你是一个检索质量标注员。你的任务是判断哪些知识库片段能够回答用户问题。\n"
        "规则：\n"
        "1. 只选出能直接回答或帮助回答问题的片段\n"
        "2. 无关、部分相关但不解决问题的片段不要选\n"
        "3. 片段来源（FTS/向量/Hybrid）仅供参考，不影响判断\n"
        "4. 严格返回 JSON 格式，不要任何额外文字\n"
        "返回格式示例：{\"relevant_ids\": [1, 3, 5]}"
    )

    user = (
        f"用户问题：{query}\n\n"
        f"以下是 {len(chunks)} 个知识库片段，请选出能回答该问题的片段：\n\n"
        + "\n".join(lines)
    )

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def parse_response(text: str, chunks: list[dict]) -> list[int]:
    """解析 LLM 返回的 JSON，提取 chunk_id 列表。"""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:]) if len(lines) > 1 else text
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        import re
        match = re.search(r'\{[^}]+\}', text)
        if match:
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                print(f"  ⚠ LLM 返回无法解析: {text[:200]}")
                return []
        else:
            print(f"  ⚠ LLM 返回无 JSON: {text[:200]}")
            return []

    ids = data.get("relevant_ids", [])
    if not isinstance(ids, list):
        return []

    result = []
    for idx in ids:
        if isinstance(idx, int) and 1 <= idx <= len(chunks):
            result.append(chunks[idx - 1]["chunk_id"])
    return result


def main():
    queries = json.loads(TEST_QUERIES_PATH.read_text(encoding="utf-8"))
    total = len(queries)
    print(f"共 {total} 道题，Pooling 三路检索 + deepseek-v4-pro 标注\n")

    for i, q in enumerate(queries):
        query_text = q["query"]
        print(f"[{i+1}/{total}] #{q['id']} {query_text[:40]}...", end=" ", flush=True)

        # 1. Pooling 三路检索
        candidates = pool_candidates(query_text, top_k=15)
        if not candidates:
            q["relevant_chunk_ids"] = []
            print("无候选 chunk")
            continue

        # 2. 构造 prompt → 调 LLM
        try:
            messages = build_prompt(query_text, candidates)
            response = call_llm(messages)
        except Exception as e:
            print(f"LLM 调用失败: {e}")
            continue

        # 3. 解析
        relevant_ids = parse_response(response, candidates)
        q["relevant_chunk_ids"] = sorted(relevant_ids)
        print(f"候选{len(candidates)}个 → {len(relevant_ids)} 个相关")

        # 4. 每次写入
        TEST_QUERIES_PATH.write_text(
            json.dumps(queries, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        time.sleep(0.5)

    # 统计
    total_labels = sum(len(q.get("relevant_chunk_ids", [])) for q in queries)
    empty = sum(1 for q in queries if not q.get("relevant_chunk_ids"))
    print(f"\n完成: {total_labels} 个标注, {empty} 道题无相关结果")


if __name__ == "__main__":
    main()
