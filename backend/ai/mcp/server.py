"""FastMCP server: Resources, Prompts, Tools for TB task management.

Multi-user support via contextvars — SSE mode extracts user identity from
query parameters (?user_id=xxx&user_name=xxx), stdio mode uses env vars.
"""

from __future__ import annotations

import contextvars
import sys
from pathlib import Path
from urllib.parse import unquote

from mcp.server.fastmcp import FastMCP

_DOMAIN_DIR = Path(__file__).resolve().parent.parent / "domain"

# Per-request user context (SSE mode)
_current_user_id: contextvars.ContextVar[str] = contextvars.ContextVar("mcp_user_id", default="")
_current_user_name: contextvars.ContextVar[str] = contextvars.ContextVar("mcp_user_name", default="")


def _get_user_id() -> str:
    return _current_user_id.get()


def _get_user_name() -> str:
    return _current_user_name.get()


def _read_domain(filename: str) -> str:
    path = _DOMAIN_DIR / filename
    if path.exists():
        return path.read_text(encoding="utf-8")
    return f"# {filename} not found\n"


# ── ASGI middleware for SSE multi-user ─────────────────────────────

class UserContextMiddleware:
    """Pure ASGI middleware — extracts user_id/user_name from query params.

    Uses pure ASGI (not BaseHTTPMiddleware) to avoid breaking SSE streaming.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Parse query string from scope
        qs = scope.get("query_string", b"").decode("utf-8", errors="ignore")
        params = {}
        for part in qs.split("&"):
            if "=" in part:
                k, v = part.split("=", 1)
                params[unquote(k)] = unquote(v)

        user_id = params.get("user_id", "").strip()
        user_name = params.get("user_name", "").strip()

        # Also check Authorization header
        if not user_id:
            headers = dict(scope.get("headers", []))
            auth = headers.get(b"authorization", b"").decode()
            if auth.startswith("Bearer "):
                user_id = auth[7:].strip()

        token_id = _current_user_id.set(user_id)
        token_name = _current_user_name.set(user_name)
        try:
            await self.app(scope, receive, send)
        finally:
            _current_user_id.reset(token_id)
            _current_user_name.reset(token_name)


# ── Resources ──────────────────────────────────────────────────────

def register_resources(mcp: FastMCP) -> None:
    """Register domain knowledge Resources from ai/domain/."""

    @mcp.resource("rule://tb/task-spec")
    def get_task_spec() -> str:
        """TB task field spec, participation tiers, customField IDs, validation rules."""
        return _read_domain("work_hour.md")

    @mcp.resource("rule://tb/work-hour")
    def get_work_hour_rules() -> str:
        """TB valid work hour classification (指派型/自主型/能力型), ratio guidance."""
        return _read_domain("work_hour.md")


# ── Prompts ────────────────────────────────────────────────────────

def register_prompts(mcp: FastMCP) -> None:
    """Register system-level Prompts."""

    @mcp.prompt()
    def tb_create(user_name: str = "用户") -> str:
        return f"""你是 Teambition 任务创建助手，用户叫 {user_name}。

## 创建流程
1. 调用 get_user_task_context 了解当前任务全景
2. 如需技术背景，调用 search_knowledge_base
3. 一问一答收集：标题(≤18字) → 工时类型 → 背景目标 → 产出 → 起止时间
4. 调用 save_task_draft 保存草稿
5. 展示草稿，等待确认
6. 调用 create_teambition_task 正式创建

## 重要规则
- 参与度 = sum(产出天数)，必须落在 [0.2, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
- 标题 ≤ 18 中文字符，产出格式: "描述(N天)"
- 创建前必须用户确认
- 规则细节见 Resources: rule://tb/task-spec, rule://tb/work-hour
"""

    @mcp.prompt()
    def tb_analyze(quarter: str = "") -> str:
        q = f"\n分析季度：{quarter}" if quarter else ""
        return f"""你是企业任务分析专家。{q}
调用 analyze_tasks 得到需求雷达、自主型建议、能力型建议、风险分析及建议草案。
如含 draft_tasks 可询问用户是否创建。
"""


# ── Tools ──────────────────────────────────────────────────────────

def _resolve_user() -> tuple[str, str]:
    """Get current user identity from contextvar, with fallback to env."""
    uid = _get_user_id()
    if not uid:
        import os
        uid = os.getenv("MCP_USER_ID", "").strip()
    name = _get_user_name()
    if not name:
        import os
        name = os.getenv("MCP_USER_NAME", "").strip()
    return uid, name


def register_tools(mcp: FastMCP) -> None:
    """Register Tools wrapping existing service-layer functions."""

    @mcp.tool()
    async def get_user_task_context() -> dict:
        """获取当前用户的所有任务上下文（任务列表、指标、父子关系树）。
        在创建 TB 单之前先调用此 Tool，了解用户任务全景。"""
        uid, name = _resolve_user()
        if not uid:
            return {"error": "未设置用户身份。SSE 模式请在 URL 加 ?user_id=xxx，stdio 模式请设 MCP_USER_ID 环境变量。"}
        from ai.tbcreate.context import load_user_task_context
        auth = {"user_id": uid, "name": name}
        ctx = load_user_task_context(auth, limit=5000)
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

    @mcp.tool()
    async def get_parent_tasks(keyword: str = "") -> dict:
        """获取可作为父任务的任务列表。可选 keyword 过滤标题。"""
        uid, _ = _resolve_user()
        if not uid:
            return {"error": "未设置用户身份"}
        from db.engine import SessionLocal
        from db.orm import ProjectTaskDetail

        session = SessionLocal()
        try:
            rows = (
                session.query(ProjectTaskDetail.parent_task_id)
                .filter(
                    ProjectTaskDetail.query_user_id == uid,
                    ProjectTaskDetail.parent_task_id.isnot(None),
                    ProjectTaskDetail.parent_task_id != "",
                )
                .distinct().all()
            )
            parent_ids = [r.parent_task_id for r in rows]
            if not parent_ids:
                return {"tasks": [], "count": 0}
            detail_rows = (
                session.query(ProjectTaskDetail.task_id, ProjectTaskDetail.content)
                .filter(ProjectTaskDetail.task_id.in_(parent_ids),
                        ProjectTaskDetail.query_user_id == uid).all()
            )
            tasks = [
                {"taskId": row.task_id, "title": (row.content or "").strip()}
                for row in detail_rows if (row.content or "").strip()
            ]
            kw = (keyword or "").strip().lower()
            if kw:
                tasks = [t for t in tasks if kw in t["title"].lower()]
            tasks.sort(key=lambda x: x["title"].lower())
            return {"tasks": tasks, "count": len(tasks)}
        finally:
            session.close()

    @mcp.tool()
    async def save_task_draft(
        title: str, work_type: str, requirement_desc: str, outputs: str,
        start_date: str = "", due_date: str = "", parent_task_id: str = "",
    ) -> dict:
        """保存 TB 任务草稿并自动校验参与度档位、标题长度等。

        Args:
            title: 任务标题 (≤18 中文字符)
            work_type: 指派型 / 自主型 / 能力型
            requirement_desc: 需求描述
            outputs: 任务产出，格式 "描述(N天)"，多项用换行分隔
            start_date: 开始日期 (YYYY-MM-DD 或 ISO 8601)
            due_date: 截止日期
            parent_task_id: 父任务 ID（可选）
        """
        import json, re
        from datetime import datetime, timezone
        from pathlib import Path

        uid, name = _resolve_user()
        if not uid:
            return {"saved": False, "error": "未设置用户身份"}

        from ai.terminal.session import user_workspace
        ws = user_workspace(uid)
        draft_dir = Path(ws["workspace_dir"])
        draft_dir.mkdir(parents=True, exist_ok=True)

        # Parse outputs
        output_list = [l.strip() for l in (outputs or "").replace("\r", "\n").split("\n") if l.strip()]
        if len(output_list) == 1 and output_list[0]:
            output_list = [o.strip() for o in output_list[0].split(",") if o.strip()]

        total_days = 0.0
        for o in output_list:
            m = re.search(r"\((\d+(?:\.\d+)?)\)", o)
            if m:
                total_days += float(m.group(1))

        TIERS = [0.2, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
        errors, warnings = [], []

        if not title.strip():
            errors.append("标题不能为空")
        else:
            cn_chars = len(re.findall(r"[一-鿿]", title))
            if cn_chars > 18:
                warnings.append(f"标题 {cn_chars} 个中文字符，超过 18 字限制")

        if work_type not in {"指派型", "自主型", "能力型"}:
            errors.append(f"工时类型必须是 指派型/自主型/能力型 之一，当前: {work_type}")
        if not output_list:
            warnings.append("未填写任务产出")
        elif not any(abs(total_days - t) < 0.02 for t in TIERS):
            warnings.append(f"参与度 {total_days} 不在标准档位 {TIERS} 中")

        def _norm(s: str, suffix: str) -> str:
            s = s.strip()
            return f"{s}T{suffix}" if s and "T" not in s else s

        start_dt = _norm(start_date, "00:00:00")
        due_dt = _norm(due_date, "23:59:59")
        if start_dt and due_dt and start_dt > due_dt:
            errors.append("开始日期不能晚于截止日期")

        valid = len(errors) == 0
        draft = {
            "title": title.strip(), "workType": work_type,
            "requirementDesc": requirement_desc.strip(), "outputs": output_list,
            "participationLevel": total_days, "dueDate": due_dt,
            "startDate": start_dt, "parentTaskId": (parent_task_id or "").strip(),
        }

        (draft_dir / "draft.json").write_text(
            json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")

        # SSE notify (best-effort)
        try:
            import requests
            requests.post("http://127.0.0.1:5001/ai/tbcreate/draft/notify",
                          json={"ownerKey": uid}, timeout=2)
        except Exception:
            pass

        return {
            "saved": valid, "draft": draft,
            "validation": {
                "valid": valid, "participationLevel": total_days,
                "tierMatch": any(abs(total_days - t) < 0.005 for t in TIERS),
                "warnings": warnings, "errors": errors,
            },
        }

    @mcp.tool()
    async def get_task_draft() -> dict:
        """读取当前保存的任务草稿。"""
        import json
        from pathlib import Path

        uid, _ = _resolve_user()
        if not uid:
            return {"error": "未设置用户身份"}
        from ai.terminal.session import user_workspace
        draft_path = Path(user_workspace(uid)["workspace_dir"]) / "draft.json"
        if draft_path.is_file():
            try:
                return {"draft": json.loads(draft_path.read_text(encoding="utf-8"))}
            except Exception:
                pass
        return {"draft": {"title": "", "workType": "指派型", "requirementDesc": "",
                          "outputs": [], "participationLevel": 1.0,
                          "dueDate": "", "startDate": "", "parentTaskId": ""}}

    @mcp.tool()
    async def create_teambition_task(
        title: str, work_type: str, requirement_desc: str, outputs: str,
        start_date: str, due_date: str, parent_task_id: str = "",
    ) -> dict:
        """正式创建 Teambition 任务。调用前请确保草稿已保存且用户已确认。"""
        import re

        uid, _ = _resolve_user()
        if not uid:
            return {"success": False, "error": "未设置用户身份"}

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
                    "taskUrl": d.get("taskUrl", ""), "message": "任务已创建"}
        return {"success": False, "error": result.get("error", "unknown error")}

    @mcp.tool()
    async def analyze_tasks(quarter: str = "") -> dict:
        """多维任务分析：需求雷达、自主型/能力型建议、风险分析、建议草案。"""
        uid, _ = _resolve_user()
        if not uid:
            return {"error": "未设置用户身份"}
        from ai.task_analysis.data import fetch_tasks
        from ai.task_analysis.retrieval import search_kb
        from ai.task_analysis.analysis import generate_report

        result = fetch_tasks(quarter=quarter, owner_key=uid)
        tasks = result.get("tasks", [])
        stats = result.get("stats", {})
        if not tasks:
            return {"error": "未获取到任务数据", "stats": stats}
        titles = [t.get("title", "") for t in tasks if t.get("title", "")]
        keywords = " ".join(titles[:10])[:200] if titles else ""
        kb_result = search_kb(keywords, top_k=10) if keywords else {"chunks": []}
        report = generate_report(tasks, stats, kb_result.get("chunks", []))
        return {"stats": stats, "report": report, "tasks_count": len(tasks)}

    @mcp.tool()
    async def search_knowledge_base(query: str, top_k: int = 10) -> dict:
        """在知识库中语义检索相关技术文档。"""
        from ai.task_analysis.retrieval import search_kb
        top = max(1, min(50, top_k))
        result = search_kb(query.strip(), top_k=top)
        return {"chunks": result.get("chunks", []), "search_query": query.strip(),
                "count": len(result.get("chunks", []))}


# ── Server factory ─────────────────────────────────────────────────

def create_server() -> FastMCP:
    """Create a fully configured FastMCP instance (no user identity — resolved per-request)."""
    mcp = FastMCP("tb-mcp")
    register_resources(mcp)
    register_prompts(mcp)
    register_tools(mcp)
    return mcp


def build_sse_app(mcp: FastMCP):
    """Build ASGI app with SSE transport + multi-user middleware."""
    from starlette.applications import Starlette
    from starlette.routing import Mount

    inner = Starlette(routes=[Mount("/", app=mcp.sse_app())])
    # Wrap with pure ASGI middleware (not Starlette Middleware to avoid SSE breakage)
    return UserContextMiddleware(inner)
