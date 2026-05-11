"""AI task assistant runtime service.

This service is intentionally model-agnostic for the first version: it prepares
per-user task context, keeps a lightweight conversation state, and creates a
structured draft file that can later be converted into a real task ticket.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from sqlalchemy import desc

from db.engine import SessionLocal
from db.orm import ProjectTaskDetail


PARTICIPATION_LEVELS = [0.2, 0.5, 1, 1.5, 2, 2.5, 3]
TASK_TYPES = ["方案设计任务", "开发实现任务", "系统联调任务"]
WORK_TYPES = ["指派型", "自主型", "能力建设型"]

_RUNTIME_DIR = Path(__file__).resolve().parent.parent / "runtime" / "ai_task_assistant"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _clean_str(value: Any) -> str:
    return str(value or "").strip()


def _safe_owner_key(owner_key: str) -> str:
    raw = _clean_str(owner_key) or "anonymous"
    return hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()[:24]


def resolve_user_identity(auth_user: Dict[str, Any]) -> Dict[str, str]:
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


def _user_root(identity: Dict[str, str]) -> Path:
    root = _RUNTIME_DIR / "users" / identity["ownerSafe"]
    (root / "conversations").mkdir(parents=True, exist_ok=True)
    (root / "drafts").mkdir(parents=True, exist_ok=True)
    return root


def _conversation_path(identity: Dict[str, str], conversation_id: str) -> Path:
    return _user_root(identity) / "conversations" / f"{conversation_id}.json"


def _draft_path(identity: Dict[str, str], conversation_id: str) -> Path:
    return _user_root(identity) / "drafts" / f"{conversation_id}.json"


def _serialize_dt(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            return _clean_str(value)
    return _clean_str(value)


def _task_status_label(status_id: Any, is_overdue: bool) -> str:
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


def _normalize_task(row: ProjectTaskDetail) -> Dict[str, Any]:
    return {
        "taskId": _clean_str(row.task_id),
        "projectId": _clean_str(row.project_id),
        "title": _clean_str(row.content) or _clean_str(row.task_id),
        "dueDate": _serialize_dt(row.due_date),
        "workHour": float(row.work_hour or 0),
        "workdayCostHour": float(row.workday_costhour or 0),
        "taskNature": _clean_str(row.task_nature),
        "statusId": row.task_flow_status_id,
        "status": _task_status_label(row.task_flow_status_id, bool(row.is_overdue)),
        "isOverdue": bool(row.is_overdue),
        "businessType": row.business_type,
    }


def load_user_task_context(auth_user: Dict[str, Any], limit: int = 80) -> Dict[str, Any]:
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
    recent_titles = [item["title"] for item in tasks[:8] if item["title"]]

    if not tasks:
        summary = "暂未从数据库读取到该用户的任务记录。助手会先按用户输入生成草稿，并提示补充必要信息。"
    else:
        type_text = "、".join(f"{name} {count} 个" for name, count in top_types)
        summary = (
            f"已读取最近 {metrics['taskCount']} 条任务：未完成 {metrics['unfinishedTaskCount']} 个，"
            f"已完成 {metrics['completedTaskCount']} 个，逾期 {metrics['overdueTaskCount']} 个。"
            f"常见任务性质：{type_text or '暂无'}。"
        )

    return {
        "identity": identity,
        "summary": summary,
        "metrics": metrics,
        "recentTasks": recent_titles,
        "tasks": tasks,
    }


def build_claude_context_markdown(auth_user: Dict[str, Any]) -> str:
    context = load_user_task_context(auth_user)
    identity = context["identity"]
    lines = [
        "# 当前用户任务上下文",
        "",
        f"- 用户：{identity.get('name') or identity.get('userId') or 'anonymous'}",
        f"- 用户 ID：{identity.get('userId') or 'unknown'}",
        f"- 摘要：{context['summary']}",
        "",
        "## 指标",
    ]
    for key, value in context["metrics"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## 最近任务"])
    for task in context["tasks"][:20]:
        due = task.get("dueDate") or "无截止时间"
        lines.append(f"- [{task.get('status')}] {task.get('title')}；截止：{due}")
    lines.extend(
        [
            "",
            "## 工作方式",
            "- 先基于上面的任务背景理解用户工作内容。",
            "- 用户输入新任务描述后，最多追问 1-3 个关键问题。",
            "- 信息足够时输出结构化任务草稿：title、taskType、workType、requirementDesc、outputs、participationLevel、missingFields。",
            "- 用户确认前不要创建真实 Teambition 任务。",
        ]
    )
    return "\n".join(lines) + "\n"


def _empty_draft() -> Dict[str, Any]:
    return {
        "title": "待生成任务单",
        "taskType": "开发实现任务",
        "workType": "指派型",
        "requirementDesc": "",
        "outputs": [],
        "participationLevel": 1,
        "missingFields": ["title", "requirementDesc", "outputs"],
        "confidence": 0.2,
    }


def _save_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_json(path: Path) -> Dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def create_task_assistant_conversation(auth_user: Dict[str, Any]) -> Dict[str, Any]:
    context = load_user_task_context(auth_user)
    identity = context["identity"]
    conversation_id = uuid.uuid4().hex[:16]
    now = _now_iso()
    assistant_text = (
        "我已经读取了你在系统里的任务上下文。"
        f"{context['summary']} 你可以直接描述想创建的新任务，我会整理成临时任务草稿。"
    )
    conversation = {
        "id": conversation_id,
        "user": identity,
        "contextSummary": context["summary"],
        "contextMetrics": context["metrics"],
        "recentTasks": context["recentTasks"],
        "messages": [
            {"role": "assistant", "content": assistant_text, "createdAt": now},
        ],
        "draft": _empty_draft(),
        "status": "collecting",
        "createdAt": now,
        "updatedAt": now,
    }
    _save_json(_conversation_path(identity, conversation_id), conversation)
    return conversation


def get_task_assistant_conversation(auth_user: Dict[str, Any], conversation_id: str) -> Dict[str, Any]:
    identity = resolve_user_identity(auth_user)
    path = _conversation_path(identity, conversation_id)
    if not path.exists():
        raise FileNotFoundError("conversation not found")
    return _load_json(path)


def _infer_task_type(text: str) -> str:
    if re.search(r"联调|协同|验证|对接|测试|系统", text):
        return "系统联调任务"
    if re.search(r"方案|设计|架构|规划|评审|调研", text):
        return "方案设计任务"
    return "开发实现任务"


def _infer_work_type(text: str) -> str:
    if re.search(r"学习|调研|分享|PoC|demo|Demo|能力|沉淀", text):
        return "能力建设型"
    if re.search(r"主动|优化|重构|复盘|改进|工具", text):
        return "自主型"
    return "指派型"


def _infer_participation(text: str) -> float:
    for level in reversed(PARTICIPATION_LEVELS):
        if str(level) in text or f"{level}人天" in text:
            return level
    if re.search(r"简单|补充|小改|排查", text):
        return 0.5
    if re.search(r"复杂|完整|重构|跨团队|系统", text):
        return 2
    return 1


def _infer_title(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip(" ，。,.")
    cleaned = re.sub(r"^(帮我|请|麻烦|需要|我要|我们要|我想|帮忙)", "", cleaned).strip(" ，。,.")
    if not cleaned:
        return "待生成任务单"
    for sep in ("，", "。", "\n", ",", "."):
        if sep in cleaned:
            cleaned = cleaned.split(sep, 1)[0]
    return cleaned[:24]


def _infer_outputs(text: str, task_type: str) -> List[str]:
    outputs: List[str] = []
    explicit = re.search(r"(产出|交付物|输出)[：:](.+)", text)
    if explicit:
        pieces = re.split(r"[、,，;；\n]", explicit.group(2))
        outputs = [piece.strip(" 。.") for piece in pieces if piece.strip(" 。.")]
    if outputs:
        return outputs[:5]
    if task_type == "方案设计任务":
        return ["方案说明文档", "关键风险与实施步骤"]
    if task_type == "系统联调任务":
        return ["联调记录", "问题闭环清单"]
    return ["功能实现代码", "自测记录"]


def _merge_draft(current: Dict[str, Any], message: str) -> Dict[str, Any]:
    text = _clean_str(message)
    base = current if isinstance(current, dict) else {}
    task_type = _infer_task_type(text) if text else base.get("taskType") or "开发实现任务"
    requirement = text or _clean_str(base.get("requirementDesc"))
    outputs = _infer_outputs(text, task_type) if text else list(base.get("outputs") or [])
    draft = {
        "title": _infer_title(text) if text else base.get("title") or "待生成任务单",
        "taskType": task_type if task_type in TASK_TYPES else "开发实现任务",
        "workType": _infer_work_type(text) if text else base.get("workType") or "指派型",
        "requirementDesc": requirement,
        "outputs": outputs,
        "participationLevel": _infer_participation(text),
    }

    missing = []
    if not draft["title"] or draft["title"] == "待生成任务单":
        missing.append("title")
    if len(draft["requirementDesc"]) < 8:
        missing.append("requirementDesc")
    if not draft["outputs"]:
        missing.append("outputs")
    confidence = max(0.35, min(0.95, 0.95 - len(missing) * 0.18))
    draft["missingFields"] = missing
    draft["confidence"] = round(confidence, 2)
    return draft


def _build_assistant_reply(draft: Dict[str, Any], context_summary: str) -> str:
    missing = draft.get("missingFields") or []
    if missing:
        labels = {
            "title": "任务标题",
            "requirementDesc": "需求背景或主要工作内容",
            "outputs": "明确产出",
        }
        ask = "、".join(labels.get(item, item) for item in missing)
        return f"我先生成了一版草稿，但还缺 {ask}。你可以补一句，我会继续完善。"
    return (
        "草稿已生成。"
        f"结合你的历史任务背景（{context_summary}），我建议先保存为临时草稿，确认后再创建正式任务单。"
    )


def send_task_assistant_message(auth_user: Dict[str, Any], conversation_id: str, content: str) -> Dict[str, Any]:
    identity = resolve_user_identity(auth_user)
    path = _conversation_path(identity, conversation_id)
    if not path.exists():
        raise FileNotFoundError("conversation not found")
    conversation = _load_json(path)
    now = _now_iso()
    message = _clean_str(content)
    if not message:
        raise ValueError("message is required")

    conversation.setdefault("messages", []).append({"role": "user", "content": message, "createdAt": now})
    draft = _merge_draft(conversation.get("draft") or {}, message)
    conversation["draft"] = draft
    reply = _build_assistant_reply(draft, _clean_str(conversation.get("contextSummary")))
    conversation["messages"].append({"role": "assistant", "content": reply, "createdAt": now})
    conversation["status"] = "drafted" if not draft.get("missingFields") else "collecting"
    conversation["updatedAt"] = now
    _save_json(path, conversation)
    return conversation


def save_task_assistant_draft(auth_user: Dict[str, Any], conversation_id: str, draft: Dict[str, Any] = None) -> Dict[str, Any]:
    identity = resolve_user_identity(auth_user)
    conversation = get_task_assistant_conversation(auth_user, conversation_id)
    final_draft = draft if isinstance(draft, dict) else conversation.get("draft") or {}
    now = _now_iso()
    temp_payload = {
        "conversationId": conversation_id,
        "user": identity,
        "draft": final_draft,
        "contextSummary": conversation.get("contextSummary"),
        "status": "draft",
        "createdAt": now,
        "updatedAt": now,
    }
    path = _draft_path(identity, conversation_id)
    _save_json(path, temp_payload)

    conversation["draft"] = final_draft
    conversation["status"] = "confirmed"
    conversation["tempDraftPath"] = str(path)
    conversation["updatedAt"] = now
    _save_json(_conversation_path(identity, conversation_id), conversation)
    return {
        "success": True,
        "conversationId": conversation_id,
        "draft": final_draft,
        "tempDraftPath": str(path),
        "message": "已保存临时任务草稿",
    }

