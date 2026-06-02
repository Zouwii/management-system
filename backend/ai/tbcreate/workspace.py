"""User workspace initialization for ai-tbcreate.

Prepares the per-user workspace directory with context files that Claude CLI
reads at startup. Separated from the ttyd session lifecycle so the workspace
can be explicitly initialized before (or independently of) a terminal session.
"""

from pathlib import Path
from typing import Any, Dict

from ai.tbcreate.context import write_user_task_context_markdown
from ai.terminal.session import user_workspace


_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "skills"


def _claude_md_template() -> str:
    """Load CLAUDE.md content from skills/2_tb_create/SKILL.md."""
    prompt_path = _PROMPTS_DIR / "2_tb_create" / "SKILL.md"
    if prompt_path.exists():
        return prompt_path.read_text(encoding="utf-8")
    # Fallback: minimal instruction
    return "# AI 任务助手\n\n你是任务创建助手，请阅读 AI_TASK_CONTEXT.md 后按规范引导用户创建任务草稿。\n"


def init_workspace(owner_key: str, auth_user: Dict[str, Any] = None) -> Dict[str, Any]:
    """Prepare the user's workspace with context files for Claude CLI.

    Creates the workspace directory and writes three files:
      - CLAUDE.md            Instructions loaded from skills/2_tb_create/SKILL.md
      - AI_TASK_CONTEXT.md   User's task data from DB
      - TASK_TICKET_RULES.md Task spec rules (copied from ai/domain/tb_rule.md)

    Idempotent: overwrites files on each call so context stays fresh.

    Args:
        owner_key: Unique user key for filesystem isolation.
        auth_user: Authenticated user dict for DB task lookup.

    Returns:
        Dict with ok, workspaceDir, ownerSafe, files written, and taskCount.
    """
    ws = user_workspace(owner_key)
    workspace_dir = Path(ws["workspace_dir"])
    workspace_dir.mkdir(parents=True, exist_ok=True)

    # 1. Write AI_TASK_CONTEXT.md from DB
    context_md = ""
    task_count = 0
    try:
        prepared = write_user_task_context_markdown(
            auth_user if isinstance(auth_user, dict) else {},
            workspace_dir=workspace_dir,
        )
        context_md = str(prepared.get("markdown") or "")
        ctx = prepared.get("context") or {}
        task_count = int((ctx.get("metrics") or {}).get("taskCount") or 0)
    except Exception as exc:
        context_md = (
            "# 当前用户任务上下文\n\n"
            "系统暂时未能读取数据库任务上下文。请先通过对话收集用户输入，再生成结构化任务草稿。\n\n"
            f"读取失败原因：{exc}\n"
        )
    (workspace_dir / "AI_TASK_CONTEXT.md").write_text(context_md, encoding="utf-8")

    # 2. Write CLAUDE.md with draft.json contract
    (workspace_dir / "CLAUDE.md").write_text(_claude_md_template(), encoding="utf-8")

    # 3. Copy TASK_TICKET_RULES.md from ai/domain/
    rules_written = False
    rules_src = Path(__file__).resolve().parent.parent / "domain" / "tb_rule.md"
    if rules_src.exists():
        (workspace_dir / "TASK_TICKET_RULES.md").write_text(
            rules_src.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        rules_written = True

    return {
        "ok": True,
        "workspaceDir": str(workspace_dir),
        "ownerSafe": ws["owner_safe"],
        "files": {
            "claudeMd": "CLAUDE.md",
            "taskContext": "AI_TASK_CONTEXT.md",
            "rules": "TASK_TICKET_RULES.md" if rules_written else None,
        },
        "taskCount": task_count,
    }
