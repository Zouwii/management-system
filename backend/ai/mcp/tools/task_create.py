"""Tool: create_teambition_task — create a TB task via DingTalk API."""


def register_tool(mcp, resolve_user_fn):
    @mcp.tool()
    async def create_teambition_task(
        title: str, work_type: str, requirement_desc: str, outputs: str,
        start_date: str, due_date: str, parent_task_id: str = "",
    ) -> dict:
        """Create a Teambition task via DingTalk API.

        IMPORTANT: Confirm with the user before calling this tool.

        Args:
            title: Task title (max 18 Chinese characters)
            work_type: Must be one of the valid work types
            requirement_desc: Format: Background: ... <newline> Goal: ... (1-2 sentences each)
            outputs: Output items separated by newline, format "desc(N days)"
                     e.g. "data-augmentation(1.0)\\nboundary-case-testing(0.5)"
                     participation = sum(N) must be in [0.2,0.5,1.0,1.5,2.0,2.5,3.0]
            start_date: Start date (YYYY-MM-DD or ISO 8601)
            due_date: Due date (YYYY-MM-DD or ISO 8601)
            parent_task_id: Optional parent task ID
        """
        import re

        uid, _ = resolve_user_fn()
        if not uid:
            return {"success": False, "error": "No user identity"}

        output_list = [l.strip() for l in (outputs or "").replace("\r", "\n").split("\n") if l.strip()]
        if len(output_list) == 1 and output_list[0]:
            output_list = [o.strip() for o in output_list[0].split(",") if o.strip()]
        total_days = sum(float(m.group(1)) for o in output_list if (m := re.search(r"\((\d+(?:\.\d+)?)\)", o)))

        def _norm(s: str, suf: str) -> str:
            s = s.strip()
            return f"{s}T{suf}" if s and "T" not in s else s

        from ai.teambition.service import create_task
        result = create_task({
            "title": title.strip(), "workType": work_type,
            "requirementDesc": requirement_desc.strip(), "outputs": output_list,
            "participationLevel": total_days,
            "startDate": _norm(start_date, "00:00:00"),
            "dueDate": _norm(due_date, "23:59:59"),
            "parentTaskId": (parent_task_id or "").strip(), "executorId": uid,
        })
        if result.get("success"):
            d = result.get("data", {})
            return {"success": True, "taskId": d.get("taskId", ""),
                    "taskUrl": d.get("taskUrl", ""), "message": "task created"}
        return {"success": False, "error": result.get("error", "unknown error")}
