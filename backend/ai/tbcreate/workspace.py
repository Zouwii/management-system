"""User workspace initialization for ai-tbcreate.

Prepares the per-user workspace directory with context files that Claude CLI
reads at startup. Separated from the ttyd session lifecycle so the workspace
can be explicitly initialized before (or independently of) a terminal session.
"""

from pathlib import Path
from typing import Any, Dict

from ai.tbcreate.context import write_user_task_context_markdown
from ai.terminal.session import user_workspace


def _claude_md_template() -> str:
    """Return the CLAUDE.md content that instructs Claude how to behave."""
    return "\n".join(
        [
            "# AI 任务助手工作区",
            "",
            "你是当前系统中的任务创建助手，职责是引导用户一步步创建 Teambition 任务草稿。",
            "",
            "## 启动行为",
            "",
            "会话开始时，先打招呼介绍自己的身份，然后提示用户可以输入「创建tb单」来开始创建任务。",
            "",
            "## 技能",
            "",
            "本工作区已启用 `tbcreate` 技能。当用户输入「创建tb单」「创建钉钉单」「创建任务」或类似意图时，",
            "技能会自动启动引导流程。",
            "",
            "在执行技能前，先阅读以下文件了解背景：",
            "- `AI_TASK_CONTEXT.md` — 用户历史任务上下文",
            "- `TASK_TICKET_RULES.md` — 任务单字段规则",
            "",
            "## draft.json 规范",
            "",
            "用户确认后，写入 `draft.json` 到当前目录。格式如下：",
            "",
            "```json",
            "{",
            '  "title": "任务标题",',
            '  "workType": "指派型",',
            '  "requirementDesc": "需求描述...",',
            '  "outputs": ["完成地图编辑功能(1.0天)", "修复导航bug(0.5天)"],',
            '  "participationLevel": 1.5,',
            '  "dueDate": "2026-05-30T23:59:59+08:00",',
            '  "startDate": "2026-05-14T00:00:00+08:00"',
            "}",
            "```",
            "",
            "字段说明：",
            "- title: 任务标题，控制在18个中文字符以内",
            '- workType: 只能是 "指派型"、"自主型"、"能力型" 之一',
            "- requirementDesc: 需求描述，说明任务背景、目标和主要工作内容",
            "- outputs: 任务产出数组，每项格式为 产出描述(N天)，N 为小数",
            "- participationLevel: 自动计算，所有产出天数之和",
            '- dueDate: 截止日期，ISO 8601 格式（如 "2026-05-30T23:59:59+08:00"），使用当天 23:59:59',
            '- startDate: 开始日期，ISO 8601 格式（如 "2026-05-14T00:00:00+08:00"），使用当天 00:00:00',
            "",
            "注意：",
            "- 请确保 JSON 格式正确，可以被 Python json.load() 解析",
            "- 所有字段都是必填的",
            '- 写完 draft.json 后，请告诉用户："草稿已保存，请在右侧面板查看并确认。"',
            "- 用户可以在右侧面板修改草稿字段，也可以让你继续修改后重新保存",
            "",
            "## api_preview.json（调试用）",
            "",
            "写完 `draft.json` 后额外生成 `api_preview.json`，模拟完整钉钉 API 请求体供用户检查。",
            "详细字段参考 `tbcreate` 技能中的模板。",
            "",
        ]
    )


def init_workspace(owner_key: str, auth_user: Dict[str, Any] = None) -> Dict[str, Any]:
    """Prepare the user's workspace with context files for Claude CLI.

    Creates the workspace directory and writes three files:
      - CLAUDE.md            Instructions + draft.json contract
      - AI_TASK_CONTEXT.md   User's task data from DB
      - TASK_TICKET_RULES.md Task drafting rules (copied from ai/rules/)

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

    # 3. Copy TASK_TICKET_RULES.md from ai/rules/
    rules_written = False
    rules_src = Path(__file__).resolve().parent.parent / "rules" / "task_ticket.md"
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
