"""SSE chat generation: retrieval → prompt → LLM stream."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Dict, Generator, List

import requests

from ai.knowledge.chat_session import add_turn, get_history

logger = logging.getLogger(__name__)

_SKILL_PROMPT_PATH = Path(__file__).resolve().parent.parent / "skills" / "3_kb_qa" / "SKILL.md"
_SYSTEM_PROMPT = (
    "你是企业内部知识助手，基于以下资料回答问题。\n"
    "回答要求：\n"
    "1. 如果提供了 TB 任务数据，优先用它回答关于人员工作、工时、进度的问题\n"
    "2. 如果提供了知识库文档，提取具体数值，不要模糊带过\n"
    "3. 区分不同数据来源，不要混为一谈\n"
    "4. 分点组织，便于阅读\n"
    "5. 资料不足时明确告知，不编造\n"
    "6. 末尾标注来源"
)

_RETRIEVAL_TOP_K = 20
_MAX_CONTEXT_TOKENS = 8000
_MAX_TB_TASKS = 30
_SKILL_PROMPT_CACHE: str | None = None


def _sse_message(payload: dict) -> str:
    data = json.dumps(payload, ensure_ascii=False)
    return f"event: message\ndata: {data}\n\n"


def _load_skill_prompt() -> str:
    """Load local knowledge Q&A skill instructions for SSE chat."""
    global _SKILL_PROMPT_CACHE
    if _SKILL_PROMPT_CACHE is not None:
        return _SKILL_PROMPT_CACHE
    try:
        _SKILL_PROMPT_CACHE = _SKILL_PROMPT_PATH.read_text(encoding="utf-8")
    except Exception:
        logger.exception("failed to load knowledge skill prompt")
        _SKILL_PROMPT_CACHE = ""
    return _SKILL_PROMPT_CACHE


def _load_config() -> dict:
    config_path = __file__.replace("/chat.py", "/../config.json")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _build_context(query: str, workspace_id: str | None = None) -> tuple[str, list[dict]]:
    """Retrieve relevant chunks and format them into a prompt context string.
    Returns (context_text, citations).
    """
    from ai.knowledge.retriever import search_hybrid, search_with_rerank

    try:
        # 通过环境变量 RERANK_ENABLED=true 启用重排
        if os.environ.get("RERANK_ENABLED", "").lower() in ("1", "true", "yes"):
            results = search_with_rerank(query, top_k=_RETRIEVAL_TOP_K, workspace_id=workspace_id)
        else:
            results = search_hybrid(query, top_k=_RETRIEVAL_TOP_K, workspace_id=workspace_id)
    except Exception:
        logger.exception("retrieval failed")
        results = []

    if not results:
        return "", []

    parts: list[str] = []
    citations: list[dict] = []
    total_tokens = 0

    for r in results:
        content = r.get("content", "")
        tk = r.get("token_count") or len(content) // 2
        if total_tokens + tk > _MAX_CONTEXT_TOKENS:
            break
        parts.append(content)
        total_tokens += tk
        citations.append({
            "source": r.get("title", ""),
            "chunk_id": r.get("chunk_id"),
            "score": r.get("score"),
        })

    context_text = "\n\n---\n\n".join(parts)
    return context_text, citations


def _find_person_names(query: str) -> list[str]:
    """Extract potential person names from the query by matching user_character.name."""
    from base.db.engine import SessionLocal
    from base.db.orm import UserCharacter

    db = SessionLocal()
    try:
        all_names = [r[0] for r in db.query(UserCharacter.name).filter(UserCharacter.name != "").all()]
    finally:
        db.close()
    return [n for n in all_names if n in query]


def _fetch_tb_tasks(query: str) -> tuple[str, list[str]]:
    """Query TB database for tasks matching person names in the query.
    Returns (tb_context_text, tb_citations).
    """
    names = _find_person_names(query)
    if not names:
        return "", []

    from base.db.engine import SessionLocal
    from base.db.orm import ProjectTask, UserCharacter

    db = SessionLocal()
    try:
        user_ids = [
            r[0] for r in
            db.query(UserCharacter.user_id).filter(UserCharacter.name.in_(names)).all()
        ]
        if not user_ids:
            return "", []

        tasks = (
            db.query(ProjectTask)
            .filter(
                ProjectTask.executor_id.in_(user_ids),
                ProjectTask.is_deleted == False,
            )
            .order_by(ProjectTask.due_date.desc())
            .limit(_MAX_TB_TASKS)
            .all()
        )

        if not tasks:
            return "", []

        lines = [f"TB 任务数据（{', '.join(names)}）："]
        for t in tasks:
            status = "完成" if t.is_done else "进行中"
            due = t.due_date.strftime("%Y-%m-%d") if t.due_date else "无截止日"
            lines.append(f"- [{status}] {t.content}（截止:{due}）")
        return "\n".join(lines), ["TB任务数据库"]
    finally:
        db.close()


def _llm_chat_url() -> str:
    cfg = _load_config()
    base = str(cfg.get("base_url") or "").strip().rstrip("/")
    if not base:
        raise RuntimeError("missing ai/config.json base_url")
    return f"{base}/v1/chat/completions"


def _llm_headers() -> dict:
    cfg = _load_config()
    api_key = str(cfg.get("api_key") or "").strip()
    if not api_key:
        raise RuntimeError("missing ai/config.json api_key")
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }


def _llm_model() -> str:
    cfg = _load_config()
    return str(cfg.get("model") or "glm-5.1").strip() or "glm-5.1"


def chat_stream(
    query: str,
    session_id: str = "",
    workspace_id: str | None = None,
) -> Generator[str, None, None]:
    """Generator that yields SSE-formatted strings for a knowledge-base chat turn.

    Yields:
      event: message  data: {"type": "text", "content": "..."}
      event: message  data: {"type": "citation", "sources": [...]}
      event: done     data: {"type": "done"}
    """
    yield _sse_message({"type": "status", "content": "加载本地知识库 skill 规则"})
    skill_prompt = _load_skill_prompt()

    # 1. Retrieve context from knowledge base + TB database
    yield _sse_message({"type": "status", "content": "检索本地向量知识库"})
    kb_context, citations = _build_context(query, workspace_id)

    yield _sse_message({"type": "status", "content": "查询本地 TB 任务数据"})
    tb_context, tb_citations = _fetch_tb_tasks(query)

    # Emit citations first so the frontend can show them early
    if citations:
        yield _sse_message({"type": "citation", "sources": citations})

    # 2. Build messages
    history = get_history(session_id) if session_id else []
    system_content = _SYSTEM_PROMPT
    if skill_prompt:
        system_content += (
            "\n\n运行环境说明：当前是 SSE 问答模式，后端已经代你调用本地"
            "向量/混合检索并把结果放入下方“知识库资料”。不要声称自己正在执行 curl。"
            "\n\n以下是本地知识库问答 skill 规则，请严格遵循：\n"
            + skill_prompt
        )

    # Merge TB data and KB context
    context_parts = []
    if tb_context:
        context_parts.append(tb_context)
    if kb_context:
        context_parts.append("知识库资料：\n---\n" + kb_context + "\n---")

    if context_parts:
        system_content += "\n\n" + "\n\n".join(context_parts)

    messages: List[Dict[str, str]] = [{"role": "system", "content": system_content}]
    messages.extend(history)
    messages.append({"role": "user", "content": query})

    # 3. Stream LLM
    yield _sse_message({"type": "status", "content": "调用模型生成回答"})
    full_reply: list[str] = []
    try:
        url = _llm_chat_url()
        headers = _llm_headers()
        model = _llm_model()

        resp = requests.post(
            url,
            headers=headers,
            json={
                "model": model,
                "messages": messages,
                "stream": True,
                "temperature": 0.3,
                "max_tokens": 4096,
            },
            timeout=60,
            stream=True,
        )
        resp.raise_for_status()

        for line in resp.iter_lines(decode_unicode=False):
            if not line:
                continue
            line_str = line.decode("utf-8") if isinstance(line, bytes) else line
            if not line_str.startswith("data:"):
                continue
            data_str = line_str[len("data:"):].strip()
            if data_str == "[DONE]":
                break
            try:
                chunk = json.loads(data_str)
                delta = (
                    chunk.get("choices", [{}])[0]
                    .get("delta", {})
                    .get("content", "")
                )
            except (json.JSONDecodeError, IndexError, KeyError):
                delta = ""
            if delta:
                full_reply.append(delta)
                yield _sse_message({"type": "text", "content": delta})

    except Exception as e:
        logger.exception("LLM stream failed")
        yield _sse_message({"type": "error", "content": f"LLM 调用失败: {str(e)}"})

    # 4. Record turn
    full_text = "".join(full_reply)
    if session_id and full_text:
        add_turn(session_id, query, full_text)

    yield "event: done\ndata: {\"type\": \"done\"}\n\n"
