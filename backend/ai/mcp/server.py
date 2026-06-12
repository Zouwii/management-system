"""FastMCP server: Resources, Prompts, Tools for TB task management.

Multi-user support via contextvars - SSE mode extracts user identity from
query parameters (?user_id=xxx or ?user_name=xxx), stdio mode uses env vars.

Resources live in mcp/resources/ (symlinks → ../../domain and ../../skills).
Tools are delegated to mcp/tools/*.py modules.
"""

from __future__ import annotations

import contextvars
import os
from pathlib import Path
from urllib.parse import unquote

from mcp.server.fastmcp import FastMCP

# ── Paths (through symlinks to external source-of-truth) ────────────────────

_RESOURCE_DIR = Path(__file__).resolve().parent / "resources"
_DOMAIN_DIR = _RESOURCE_DIR / "domain"    # → ../../domain  (ai/domain/)
_SKILL_DIR = _RESOURCE_DIR / "skills"      # → ../../skills  (ai/skills/)

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


def _read_skill(filename: str) -> str:
    path = _SKILL_DIR / filename
    if path.exists():
        return path.read_text(encoding="utf-8")
    return f"# {filename} not found\n"


# ── User resolution (shared with tools) ─────────────────────────────────────

def _resolve_user_id_from_name(name: str) -> str:
    """Look up user_id from UserCharacter table by Chinese name."""
    if not name or not name.strip():
        return ""
    try:
        from base.db.engine import SessionLocal
        from base.db.orm import UserCharacter as DbUserCharacter
        db = SessionLocal()
        try:
            row = db.query(DbUserCharacter.user_id).filter(DbUserCharacter.name == name.strip()).first()
            if row and row[0]:
                return str(row[0]).strip()
        finally:
            db.close()
    except Exception:
        pass
    return ""


def _resolve_user() -> tuple[str, str]:
    """Resolve uid/name from contextvars, falling back to env vars."""
    uid = _get_user_id()
    if not uid:
        uid = os.getenv("MCP_USER_ID", "").strip()
    name = _get_user_name()
    if not name:
        name = os.getenv("MCP_USER_NAME", "").strip()

    if uid and not name:
        try:
            from base.db.engine import SessionLocal
            from base.db.orm import UserCharacter as DbUserCharacter
            db = SessionLocal()
            try:
                row = db.query(DbUserCharacter.name).filter(DbUserCharacter.user_id == uid).first()
                if row and row[0]:
                    name = str(row[0]).strip()
            finally:
                db.close()
        except Exception:
            pass

    return uid, name


# ── ASGI middleware ──────────────────────────────────────────────────────────

class UserContextMiddleware:
    """ASGI middleware - extracts user identity from query params.

    Accepts user_id or user_name (or both). If only name is given,
    auto-resolves user_id from the database.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        qs = scope.get("query_string", b"").decode("utf-8", errors="ignore")
        params = {}
        for part in qs.split("&"):
            if "=" in part:
                k, v = part.split("=", 1)
                params[unquote(k)] = unquote(v)

        user_id = params.get("user_id", "").strip()
        user_name = params.get("user_name", "").strip()

        if not user_id:
            headers = dict(scope.get("headers", []))
            auth = headers.get(b"authorization", b"").decode()
            if auth.startswith("Bearer "):
                user_id = auth[7:].strip()

        if user_name and not user_id:
            user_id = _resolve_user_id_from_name(user_name)

        token_id = _current_user_id.set(user_id)
        token_name = _current_user_name.set(user_name)
        try:
            await self.app(scope, receive, send)
        finally:
            _current_user_id.reset(token_id)
            _current_user_name.reset(token_name)


# ── Resources (domain rules + skill workflows) ───────────────────────────────

def register_resources(mcp: FastMCP) -> None:

    # -- Domain rules (source: ai/domain/)

    @mcp.resource("rule://tb/task-spec")
    def get_task_spec() -> str:
        """TB task field spec, participation tiers, customField IDs, validation rules."""
        return _read_domain("tb_rule.md")

    @mcp.resource("rule://tb/work-hour")
    def get_work_hour_rules() -> str:
        """TB valid work hour classification (assign/auto/capability), ratio guidance."""
        return _read_domain("work_hour.md")

    # -- Skill workflows (source: ai/skills/)

    @mcp.resource("skill://tb/create")
    def get_skill_create() -> str:
        """TB task creation workflow: Q&A flow, draft format, panel sync rules.

        Read when user says "create TB task" / "建单子" / "创建任务".
        Contains Mode A (quick draft from context) and Mode B (guided 5-step Q&A).
        """
        return _read_skill("2_tb_create/SKILL.md")

    @mcp.resource("skill://tb/analyze")
    def get_skill_analyze() -> str:
        """Multi-dimension task analysis report spec: 4 modules, JSON output format.

        Read when user says "analyze tasks" / "分析任务" / "开始分析".
        """
        return _read_skill("1_tb_analysis/SKILL.md")

    @mcp.resource("skill://tb/kb-qa")
    def get_skill_kb_qa() -> str:
        """Knowledge base Q&A workflow: search method, answer rules, citation format."""
        return _read_skill("3_kb_qa/SKILL.md")

    @mcp.resource("skill://tb/keyword-extract")
    def get_skill_keyword_extract() -> str:
        """Keyword extraction rules: extract 10-15 technical terms from task list."""
        return _read_skill("1-1_keyword_extract/SKILL.md")

    @mcp.resource("skill://ops/server")
    def get_skill_server_ops() -> str:
        """Server operations: SSH connection, log viewing, DB queries, restart.

        Read when user says "connect to server" / "连接服务器" / "查看日志"
        / "查数据库" / "restart service" / "重启服务".
        """
        return _read_skill("0_server_ops/SKILL.md")


# ── Prompts ──────────────────────────────────────────────────────────────────

def register_prompts(mcp: FastMCP) -> None:

    @mcp.prompt()
    def tb_create(user_name: str = "user") -> str:
        return f"""You are a Teambition task creation assistant. User: {user_name}.

This is the **MCP direct creation path** — create tasks in CLI without SSE/frontend interaction.
All work is done entirely in the terminal conversation with the user.

## Choose mode based on conversation context

### Mode A: Quick draft (user has already discussed the task)

If the user has already described the task in previous conversation turns, do NOT ask them
to repeat. Instead:

1. Call get_user_task_context to understand their current workload.
2. Extract from conversation: title (<=18 Chinese chars), work type, background, goal, outputs.
3. Draft outputs: "desc(N days)" format, 2-5 items. participation=sum(N) in [0.2,0.5,1.0,1.5,2.0,2.5,3.0].
4. Show the complete draft and ask "Shall I create this? Or adjust anything?"
5. If confirmed, call create_teambition_task.

### Mode B: Guided Q&A (brand new task, no context)

If this is a fresh request with minimal context, collect info one question at a time:
1. Title (≤18 Chinese chars)
2. Work type (指派型/自主型/能力型)
3. Background and goal
4. Outputs (generate suggested list, format "desc(N days)")
5. Start/end dates (default: today → end of month)
After all collected, show draft → confirm → call create_teambition_task.

## Important rules
- **This is pure CLI mode — no SSE, no frontend, no draft.json.** Call create_teambition_task directly.
- Never create a task without user's explicit confirmation.
- participation = sum(output days), must be in [0.2, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
- After successful creation, show taskId and ask if user wants to create another task.

For field spec details, read Resource: rule://tb/task-spec
For work hour classification, read Resource: rule://tb/work-hour
"""


# ── Tools ────────────────────────────────────────────────────────────────────

def register_tools(mcp: FastMCP) -> None:
    from ai.mcp.tools.task_context import register_tool as reg_ctx
    from ai.mcp.tools.task_create import register_tool as reg_create
    from ai.mcp.tools.kb_search import register_tool as reg_kb
    from ai.mcp.tools.workhour import register_tool as reg_wh

    reg_ctx(mcp, _resolve_user)
    reg_create(mcp, _resolve_user)
    reg_kb(mcp, _resolve_user)
    reg_wh(mcp, _resolve_user)


# ── Server factory ───────────────────────────────────────────────────────────

def create_server() -> FastMCP:
    # host="0.0.0.0" prevents FastMCP from auto-enabling DNS rebinding
    # protection (which only allows localhost Host headers). We use uvicorn
    # for network binding; FastMCP's host parameter is only used to decide
    # whether to enable transport_security for localhost.
    mcp = FastMCP("tb-mcp", host="0.0.0.0")
    register_resources(mcp)
    register_prompts(mcp)
    register_tools(mcp)
    return mcp


def build_sse_app(mcp: FastMCP):
    from starlette.applications import Starlette
    from starlette.routing import Mount

    inner = Starlette(routes=[Mount("/", app=mcp.sse_app())])
    return UserContextMiddleware(inner)
