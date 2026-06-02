"""步骤2: 知识库检索。

基于任务关键词搜索 kb_chunks，返回相关文档切片。
前端可手动调整关键词重新检索。
"""

from __future__ import annotations

from typing import Any, Dict, List


def search_kb(
    keywords: str,
    top_k: int = 20,
    workspace_id: str | None = None,
) -> Dict[str, Any]:
    """搜索知识库，返回相关切片。

    Args:
        keywords: 搜索关键词。
        top_k: 返回数量，默认 20。
        workspace_id: 限定知识库，默认所有已启用。

    Returns:
        {chunks: [...], search_query: "..."}
    """
    from ai.knowledge.retriever import search_hybrid

    if not keywords or not keywords.strip():
        return {"chunks": [], "search_query": ""}

    try:
        results = search_hybrid(keywords.strip(), top_k=top_k, workspace_id=workspace_id)
    except Exception:
        return {"chunks": [], "search_query": keywords}

    chunks = [
        {
            "chunkId": r.get("chunk_id"),
            "source": r.get("title", ""),
            "content": r.get("content", ""),
            "score": round(r.get("score", 0), 4),
        }
        for r in results
    ]

    return {"chunks": chunks, "search_query": keywords}
