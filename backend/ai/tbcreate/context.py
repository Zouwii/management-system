"""AI task context preparation.

Reads task data from the database and writes markdown context files
into the user's AI workspace. Never mutates task rows.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import desc

from db.engine import SessionLocal
from db.orm import ProjectTaskDetail

REQUIREMENT_DESC_CUSTOMFIELD_ID = "686273700d15b3f835491a2e"
TASK_OUTPUT_CUSTOMFIELD_ID = "6862737e3b781c68b3181925"

_RUNTIME_DIR = Path(__file__).resolve().parent.parent.parent / "runtime" / "ai_task_assistant"


def _clean_str(value: Any) -> str:
    """Coerce any value to a stripped string."""
    return str(value or "").strip()


def _safe_owner_key(owner_key: str) -> str:
    """Hash an owner_key into a filesystem-safe 24-char hex string."""
    import hashlib

    raw = _clean_str(owner_key) or "anonymous"
    return hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()[:24]


def resolve_user_identity(auth_user: Dict[str, Any]) -> Dict[str, str]:
    """Extract user identity from an auth_user dict.

    Returns a dict with userId, name, ownerKey, and ownerSafe (SHA256 hash).
    """
    user = auth_user if isinstance(auth_user, dict) else {}
    user_id = _clean_str(user.get("user_id") or user.get("userid") or user.get("id"))
    name = _clean_str(user.get("name") or user.get("nick") or user.get("nickname") or user.get("user_name"))
    owner_key = user_id or name or "anonymous"
    return {
        "userId": user_id,
        "name": name,
        "ownerKey": owner_key,
        "ownerSafe": _safe_owner_key(owner_key),
    }


def _serialize_dt(value: Any) -> str:
    """Serialize a datetime or string value to ISO format string."""
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            return _clean_str(value)
    return _clean_str(value)


def _as_dict_list(value: Any) -> List[Dict[str, Any]]:
    """Normalize a value into a list of dicts (for customFields parsing)."""
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        return [value]
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
        except Exception:
            return []
        return _as_dict_list(parsed)
    return []


def _extract_custom_field_text(custom_fields: Any, field_id: str) -> str:
    """Extract a text value from a DingTalk customFields array by field_id."""
    for cf in _as_dict_list(custom_fields):
        cfid = _clean_str(cf.get("customFieldId") or cf.get("customfieldId"))
        if cfid != field_id:
            continue
        value = cf.get("value")
        if isinstance(value, list) and value:
            node = value[0]
            if isinstance(node, dict):
                text = _clean_str(
                    node.get("title")
                    or node.get("value")
                    or node.get("metaString")
                    or node.get("text")
                    or node.get("customFieldValueId")
                )
                if text:
                    return text
            else:
                text = _clean_str(node)
                if text:
                    return text
        if isinstance(value, dict):
            text = _clean_str(
                value.get("title")
                or value.get("value")
                or value.get("metaString")
                or value.get("text")
            )
            if text:
                return text
        text = _clean_str(value)
        if text:
            return text
    return ""


def _extract_custom_field_outputs(custom_fields: Any, field_id: str) -> List[str]:
    """Extract task outputs from a DingTalk customFields array as a list."""
    text = _extract_custom_field_text(custom_fields, field_id)
    if not text:
        return []
    parts = [piece.strip(" 。.;.;,\n") for piece in text.replace("\r", "\n").split("\n")]
    out = [piece for piece in parts if piece]
    return out if out else [text]


def _normalize_task(row: ProjectTaskDetail) -> Dict[str, Any]:
    """Convert a ProjectTaskDetail ORM row into a normalized dict."""
    custom_fields = row.custom_fields_json
    if not custom_fields:
        try:
            raw_json = json.loads(row.raw_json) if row.raw_json else {}
        except Exception:
            raw_json = {}
        custom_fields = raw_json.get("customFields") or raw_json.get("customfields") or []
    parent_task_id = _clean_str(row.parent_task_id or row.parent_id)
    return {
        "taskId": _clean_str(row.task_id),
        "projectId": _clean_str(row.project_id),
        "title": _clean_str(row.content) or _clean_str(row.task_id),
        "content": _clean_str(row.content),
        "note": _clean_str(getattr(row, "note", "") or ""),
        "requirementDesc": _extract_custom_field_text(custom_fields, REQUIREMENT_DESC_CUSTOMFIELD_ID),
        "taskOutputs": _extract_custom_field_outputs(custom_fields, TASK_OUTPUT_CUSTOMFIELD_ID),
        "dueDate": _serialize_dt(row.due_date),
        "workHour": float(row.work_hour or 0),
        "workdayCostHour": float(row.workday_costhour or 0),
        "taskNature": _clean_str(row.task_nature),
        "statusId": row.task_flow_status_id,
        "status": _task_status_label(row.task_flow_status_id, bool(row.is_overdue)),
        "isOverdue": bool(row.is_overdue),
        "businessType": row.business_type,
        "parentTaskId": parent_task_id,
        "parentId": _clean_str(row.parent_id),
    }


def _task_status_label(status_id: Any, is_overdue: bool) -> str:
    """Map a DingTalk task status ID to a human-readable Chinese label."""
    try:
        status = int(status_id)
    except Exception:
        status = -1
    if status == 4:
        return "已完成"
    if is_overdue:
        return "逾期"
    if status == 0:
        return "创建中"
    if status == 1:
        return "未完成"
    if status == 2:
        return "待评审"
    if status == 3:
        return "评审中"
    if status == 5:
        return "搁置"
    return "进行中"


def load_user_task_context(auth_user: Dict[str, Any], limit: int = 5000) -> Dict[str, Any]:
    """Read the current user's task rows from DB and build a context snapshot.

    Args:
        auth_user: Authenticated user dict (must contain user_id).
        limit: Maximum number of task rows to fetch (default 5000).

    Returns:
        A dict with identity, summary, metrics, recentTasks, and task tree structures.
    """
    identity = resolve_user_identity(auth_user)
    user_id = identity["userId"]
    tasks: List[Dict[str, Any]] = []
    if user_id:
        session = SessionLocal()
        try:
            rows = (
                session.query(ProjectTaskDetail)
                .filter(ProjectTaskDetail.query_user_id == user_id)
                .order_by(desc(ProjectTaskDetail.fetched_at), desc(ProjectTaskDetail.due_date))
                .limit(int(limit))
                .all()
            )
            tasks = [_normalize_task(row) for row in rows]
        finally:
            session.close()

    metrics = {
        "taskCount": len(tasks),
        "completedTaskCount": sum(1 for item in tasks if item["status"] == "已完成"),
        "unfinishedTaskCount": sum(1 for item in tasks if item["status"] != "已完成"),
        "overdueTaskCount": sum(1 for item in tasks if item["isOverdue"]),
        "scheduledHours": round(sum(float(item.get("workHour") or 0) for item in tasks), 2),
    }
    top_types = Counter(item["taskNature"] or "未标注" for item in tasks).most_common(3)

    task_index = {item["taskId"]: item for item in tasks if item.get("taskId")}
    children_by_parent: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    roots: List[Dict[str, Any]] = []
    orphans: List[Dict[str, Any]] = []
    for task in tasks:
        parent_key = _clean_str(task.get("parentTaskId") or task.get("parentId"))
        if parent_key:
            children_by_parent[parent_key].append(task)
            if parent_key not in task_index:
                orphans.append(task)
        else:
            roots.append(task)

    def _task_sort_key(item: Dict[str, Any]) -> Tuple[int, str, str]:
        due = _clean_str(item.get("dueDate"))
        return (0 if due else 1, due or "9999-12-31", _clean_str(item.get("taskId")))

    for group in children_by_parent.values():
        group.sort(key=_task_sort_key)
    roots.sort(key=_task_sort_key)
    orphans = [item for item in orphans if _clean_str(item.get("taskId"))]

    if not tasks:
        summary = "暂未从数据库读取到该用户的任务记录。后续会先基于新任务描述生成草稿，不会修改已有任务单。"
    else:
        type_text = "、".join(f"{name} {count} 个" for name, count in top_types)
        summary = (
            f"已读取 {metrics['taskCount']} 条任务：未完成 {metrics['unfinishedTaskCount']} 个，"
            f"已完成 {metrics['completedTaskCount']} 个，逾期 {metrics['overdueTaskCount']} 个。"
            f"常见任务性质：{type_text or '暂无'}。"
        )

    return {
        "identity": identity,
        "summary": summary,
        "metrics": metrics,
        "recentTasks": tasks,
        "roots": roots,
        "childrenByParent": children_by_parent,
        "orphans": orphans,
        "taskIndex": task_index,
    }


def _trim_text(value: Any, limit: int = 320) -> str:
    """Truncate text to a character limit, appending '...' if truncated."""
    text = _clean_str(value)
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _render_task_lines(
    task: Dict[str, Any], task_index: Dict[str, Dict[str, Any]], indent: str = ""
) -> List[str]:
    """Render a single task as formatted markdown lines."""
    lines = []
    title = _trim_text(task.get("title") or task.get("taskId"), 80)
    lines.append(f"{indent}- [{task.get('status') or '未知'}] {title}")
    lines.append(f"{indent}  - taskId: {task.get('taskId') or ''}")
    if task.get("parentTaskId"):
        parent = task_index.get(_clean_str(task.get("parentTaskId")))
        parent_label = _trim_text(parent.get("title"), 80) if parent else _clean_str(task.get("parentTaskId"))
        lines.append(f"{indent}  - parent: {parent_label}")
    if task.get("dueDate"):
        lines.append(f"{indent}  - dueDate: {task.get('dueDate')}")
    if task.get("workHour") is not None:
        lines.append(f"{indent}  - workHour: {task.get('workHour')}")
    if task.get("taskNature"):
        lines.append(f"{indent}  - taskNature: {task.get('taskNature')}")
    if task.get("businessType") is not None:
        lines.append(f"{indent}  - businessType: {task.get('businessType')}")
    content = _trim_text(task.get("content"), 320)
    note = _trim_text(task.get("note"), 320)
    requirement_desc = _trim_text(task.get("requirementDesc"), 320)
    task_outputs = task.get("taskOutputs") or []
    if content:
        lines.append(f"{indent}  - content: {content}")
    if note and note != content:
        lines.append(f"{indent}  - note: {note}")
    if requirement_desc:
        lines.append(f"{indent}  - requirementDesc: {requirement_desc}")
    if task_outputs:
        lines.append(f"{indent}  - taskOutputs: {'; '.join(_trim_text(item, 120) for item in task_outputs[:5])}")
    return lines


def _render_task_tree(
    task: Dict[str, Any],
    children_by_parent: Dict[str, List[Dict[str, Any]]],
    task_index: Dict[str, Dict[str, Any]],
    depth: int = 0,
) -> List[str]:
    """Recursively render a task and its child tasks as markdown lines."""
    indent = "  " * depth
    lines = _render_task_lines(task, task_index, indent=indent)
    for child in children_by_parent.get(_clean_str(task.get("taskId")), []):
        lines.extend(_render_task_tree(child, children_by_parent, task_index, depth + 1))
    return lines


def render_user_task_context_markdown(context: Dict[str, Any]) -> str:
    """Build a complete markdown document from a user task context dict.

    The output is written to AI_TASK_CONTEXT.md in the user's workspace and
    read by the Claude CLI as startup context.
    """
    identity = context.get("identity") or {}
    metrics = context.get("metrics") or {}
    roots = list(context.get("roots") or [])
    children_by_parent = context.get("childrenByParent") or {}
    task_index = context.get("taskIndex") or {}
    orphans = list(context.get("orphans") or [])
    tasks = list(context.get("recentTasks") or [])

    lines = [
        "# 当前用户任务上下文",
        "",
        "## 说明",
        "- 这是一份只读上下文，用于聊天前给 AI 提供任务背景。",
        "- 这里只借鉴现有数据库中的文字描述和父子任务关系，不会修改任何任务单。",
        "",
        "## 基本信息",
        f"- 用户：{identity.get('name') or identity.get('userId') or 'anonymous'}",
        f"- 用户 ID：{identity.get('userId') or 'unknown'}",
        f"- 读取时间：{datetime.now(timezone.utc).replace(microsecond=0).isoformat()}",
        f"- 摘要：{context.get('summary') or ''}",
        "",
        "## 指标",
    ]
    for key, value in metrics.items():
        lines.append(f"- {key}: {value}")

    lines.extend(["", "## 最近任务"])
    if tasks:
        for task in tasks:
            lines.extend(_render_task_lines(task, task_index))
    else:
        lines.append("- 无任务记录")

    lines.extend(["", "## 父子任务关系"])
    if roots:
        for task in roots:
            lines.extend(_render_task_tree(task, children_by_parent, task_index))
    else:
        lines.append("- 未找到可作为根节点的任务")

    if orphans:
        lines.extend(["", "## 孤立子任务"])
        for task in orphans:
            lines.append(f"- {task.get('title') or task.get('taskId')}")
            if task.get("parentTaskId"):
                lines.append(f"  - parentTaskId: {task.get('parentTaskId')}")

    lines.extend(
        [
            "",
            "## 给 AI 的使用规则",
            "- 优先参考任务标题、content、note 和父子任务结构。",
            "- 生成新任务草稿时，只做归纳整理，不要改写既有任务内容。",
            "- 如果历史任务信息不足，可以追问用户，而不是猜测数据库里不存在的事实。",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _prepare_workspace_dir(identity: Dict[str, str], workspace_dir: Optional[Path] = None) -> Path:
    """Ensure the user's AI workspace directory exists, creating it if needed."""
    if workspace_dir is None:
        workspace_dir = _RUNTIME_DIR / "users" / identity["ownerSafe"] / "workspaces" / "default"
    workspace_dir.mkdir(parents=True, exist_ok=True)
    return workspace_dir


def write_user_task_context_markdown(
    auth_user: Dict[str, Any], workspace_dir: Optional[Path] = None
) -> Dict[str, Any]:
    """Load user task context from DB and write AI_TASK_CONTEXT.md to workspace.

    CLAUDE.md is written separately by workspace.init_workspace().

    Args:
        auth_user: Authenticated user dict.
        workspace_dir: Optional explicit workspace path. Auto-derived if not given.

    Returns:
        Dict with identity, context, workspaceDir, contextMarkdownPath, and markdown.
    """
    context = load_user_task_context(auth_user)
    identity = context["identity"]
    workspace = _prepare_workspace_dir(identity, workspace_dir)
    markdown = render_user_task_context_markdown(context)
    context_path = workspace / "AI_TASK_CONTEXT.md"
    context_path.write_text(markdown, encoding="utf-8")
    return {
        "identity": identity,
        "context": context,
        "workspaceDir": str(workspace),
        "contextMarkdownPath": str(context_path),
        "markdown": markdown,
    }
