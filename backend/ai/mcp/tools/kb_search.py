"""Tool: search_knowledge_base — semantic search in company knowledge base."""


def register_tool(mcp, resolve_user_fn):
    @mcp.tool()
    async def search_knowledge_base(query: str, top_k: int = 10) -> dict:
        """Semantic search in the company knowledge base (full-text + vector hybrid).

        Args:
            query: Search keywords or question
            top_k: Number of results (default 10)
        """
        from ai.task_analysis.retrieval import search_kb
        top = max(1, min(50, top_k))
        result = search_kb(query.strip(), top_k=top)
        return {"chunks": result.get("chunks", []), "search_query": query.strip(),
                "count": len(result.get("chunks", []))}
