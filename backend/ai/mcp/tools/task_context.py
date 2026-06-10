"""Tool: get_user_task_context — user's TB task list, metrics, parent-child tree."""


def register_tool(mcp, resolve_user_fn):
    @mcp.tool()
    async def get_user_task_context() -> dict:
        """Get current user task context: task list, metrics, parent-child tree.

        Call this first before creating a TB task to understand the user's workload.
        """
        uid, name = resolve_user_fn()
        if not uid:
            return {"error": "No user identity. SSE mode: add ?user_name=xxx to URL. stdio mode: set MCP_USER_ID env var."}
        from ai.tbcreate.context import load_user_task_context
        auth = {"user_id": uid, "name": name}
        ctx = load_user_task_context(auth, limit=100)
        return {
            "identity": ctx.get("identity", {}),
            "summary": ctx.get("summary", ""),
            "metrics": ctx.get("metrics", {}),
            "tasks": [
                {
                    "taskId": t.get("taskId"), "title": t.get("title"),
                    "status": t.get("status"), "taskNature": t.get("taskNature"),
                    "workHour": t.get("workHour"), "isOverdue": t.get("isOverdue"),
                    "dueDate": t.get("dueDate"), "parentTaskId": t.get("parentTaskId"),
                }
                for t in (ctx.get("recentTasks") or [])[:100]
            ],
        }
