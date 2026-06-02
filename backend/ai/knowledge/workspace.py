"""Knowledge base Q&A workspace initialization.

Prepares the per-user workspace directory with context files that Claude CLI
reads at startup for the knowledge-base Q&A assistant.
"""

from pathlib import Path
from typing import Any, Dict

from ai.terminal.session import user_workspace


_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "skills"


def _claude_md_template() -> str:
    """Load CLAUDE.md content from skills/3_kb_qa/SKILL.md."""
    prompt_path = _PROMPTS_DIR / "3_kb_qa" / "SKILL.md"
    if prompt_path.exists():
        return prompt_path.read_text(encoding="utf-8")
    return "# 知识库问答助手\n\n你是知识库问答助手，请基于知识库文档回答用户问题。\n"


def init_knowledge_workspace(owner_key: str, auth_user: Dict[str, Any] = None) -> Dict[str, Any]:
    """Prepare the user's workspace with knowledge base Q&A context.

    Creates the workspace directory, writes CLAUDE.md, and grants bash permissions
    so Claude doesn't ask for approval on every curl/search command.

    Args:
        owner_key: Unique user key for filesystem isolation.
        auth_user: User auth info (unused, but required to match caller signature).

    Returns:
        Dict with ok, workspaceDir, ownerSafe.
    """
    ws = user_workspace(owner_key)
    workspace_dir = Path(ws["workspace_dir"])
    workspace_dir.mkdir(parents=True, exist_ok=True)
    claude_dir = Path(ws["claude_dir"])
    claude_dir.mkdir(parents=True, exist_ok=True)

    # Write CLAUDE.md with knowledge Q&A instructions
    (workspace_dir / "CLAUDE.md").write_text(_claude_md_template(), encoding="utf-8")

    return {
        "ok": True,
        "workspaceDir": str(workspace_dir),
        "ownerSafe": ws["owner_safe"],
    }
