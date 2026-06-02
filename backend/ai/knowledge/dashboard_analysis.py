"""Dashboard analysis: 4-module task analysis via a single structured LLM call.

Prompt template is read from ai/skills/1_tb_analysis/SKILL.md
— edit that file to adjust analysis rules without redeploying code.
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, List

import requests

logger = logging.getLogger(__name__)

_SKILL_PATH = (
    Path(__file__).resolve().parent.parent
    / "skills" / "1_tb_analysis" / "SKILL.md"
)


def _load_prompt() -> str:
    """Read the analysis prompt from the task-analysis SKILL.md file.

    The file supports {task_context}, {work_hour_stats}, {kb_context}, and
    {ratio_stats} placeholders, filled via Python's str.format().
    """
    raw = _SKILL_PATH.read_text(encoding="utf-8")
    # Strip YAML frontmatter
    if raw.startswith("---"):
        end = raw.find("---", 3)
        if end != -1:
            raw = raw[end + 3:]
    return raw.strip()


def _load_config() -> dict:
    config_path = __file__.replace("/dashboard_analysis.py", "/../config.json")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _llm_base() -> str:
    cfg = _load_config()
    base = str(cfg.get("base_url") or "").strip().rstrip("/")
    if not base:
        raise RuntimeError("missing ai/config.json base_url")
    return base


def _llm_api_key() -> str:
    cfg = _load_config()
    key = str(cfg.get("api_key") or "").strip()
    if not key:
        raise RuntimeError("missing ai/config.json api_key")
    return key


def _llm_model() -> str:
    cfg = _load_config()
    return str(cfg.get("model") or "glm-5.1").strip() or "glm-5.1"


_DEBUG_LOG_DIR = Path(__file__).resolve().parent.parent.parent / "runtime" / "logs"


def _save_debug_log(raw: str) -> None:
    """Save raw LLM output to runtime/logs/dashboard_llm_{ts}.json for debugging."""
    try:
        _DEBUG_LOG_DIR.mkdir(parents=True, exist_ok=True)
        ts = int(time.time() * 1000)
        path = _DEBUG_LOG_DIR / f"dashboard_llm_{ts}.json"
        path.write_text(raw, encoding="utf-8")
        logger.info("saved LLM raw output to %s (%d chars)", path.name, len(raw))
    except Exception as exc:
        logger.warning("failed to save LLM debug log: %s", exc)


def analyze_dashboard(
    tasks: List[Dict[str, Any]],
    work_hour_stats: Dict[str, Any],
    kb_chunks: List[Dict[str, Any]],
) -> dict:
    """Generate all 6 analysis modules via a single LLM call.

    Args:
        tasks: List of task summaries (id, title, content, progress, etc.)
        work_hour_stats: Aggregated work hour breakdown
        kb_chunks: KB retrieval results

    Returns:
        Dict with 6 module results, or {"error": "..."}
    """
    # Build task context
    task_lines: list[str] = []
    for t in tasks[:20]:
        task_lines.append(
            f"- [{t.get('title', '')}] 进度:{t.get('progress', 0)}% "
            f"逾期:{'是' if t.get('isOverdue') else '否'} "
            f"工时:{t.get('workHour') or '-'}d "
            f"类型:{t.get('taskNature') or '-'}"
        )
    task_context = "\n".join(task_lines) if task_lines else "无任务数据"

    # Build KB context (top 5, truncated)
    kb_parts: list[str] = []
    for i, k in enumerate(kb_chunks[:5]):
        source = k.get("source", "未知")
        content = k.get("content", "")
        if len(content) > 800:
            content = content[:800] + "..."
        kb_parts.append(f"[规范{i+1}: {source}]\n{content}")
    kb_context = "\n\n---\n\n".join(kb_parts) if kb_parts else "无知识库参考"

    # Format ratio stats for prompt
    ratio_stats = (
        f"指派型:{work_hour_stats.get('assigned_pct', 0)}%, "
        f"自主型:{work_hour_stats.get('autonomous_pct', 0)}%, "
        f"能力型:{work_hour_stats.get('capability_pct', 0)}%"
    )

    prompt = _load_prompt()
    prompt = prompt.replace("{task_context}", task_context)
    prompt = prompt.replace("{work_hour_stats}", (
        f"总任务数:{work_hour_stats.get('total_tasks', 0)}, "
        f"已完成:{work_hour_stats.get('done_count', 0)}, "
        f"逾期:{work_hour_stats.get('overdue_count', 0)}"
    ))
    prompt = prompt.replace("{kb_context}", kb_context)
    prompt = prompt.replace("{ratio_stats}", ratio_stats)

    # Call LLM
    try:
        url = f"{_llm_base()}/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {_llm_api_key()}",
        }

        resp = requests.post(
            url,
            headers=headers,
            json={
                "model": _llm_model(),
                "messages": [
                    {"role": "system", "content": "你是一个专业的企业任务分析助手，总是严格按照要求的 JSON 格式回答，不要添加任何解释。"},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.2,
                "max_tokens": 4096,
            },
            timeout=120,
        )
        resp.raise_for_status()

        body = resp.json()
        content = (
            body.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )

        if not content:
            return {"error": "LLM returned empty response"}

        # 调试：保存 LLM 原始输出到 runtime/logs/ 方便排查
        _save_debug_log(content)

        result = _parse_json_robust(content)
        if result is None:
            return {"error": "LLM 返回格式异常", "raw": content[:500]}

        # Ensure all 6 modules present
        expected = [
            "requirement_radar", "tech_debt_auditor", "performance_balancer",
            "growth_booster", "efficiency_transformer", "risk_warning_engine",
        ]
        for module in expected:
            if module not in result:
                result[module] = {}
        return result

    except requests.RequestException as e:
        logger.exception("LLM request failed")
        return {"error": f"LLM 调用失败: {str(e)}"}


def _parse_json_robust(raw: str) -> dict | None:
    """Try multiple strategies to extract valid JSON from LLM output."""
    raw = raw.strip()
    if not raw:
        return None

    strategies = [
        # 1. Direct parse
        lambda s: json.loads(s),
        # 2. Strip markdown code blocks (```json ... ```)
        lambda s: json.loads(re.sub(r"^```(?:json)?\s*\n?", "", re.sub(r"\n```\s*$", "", s.strip()))),
        # 3. Find outermost { ... } with regex
        lambda s: json.loads(re.search(r"\{.*\}", s.strip(), re.DOTALL).group()),
        # 4. Try fixing trailing commas in objects/arrays
        lambda s: json.loads(re.sub(r",\s*([\]}])", r"\1", s)),
        # 5. Combine code block stripping + trailing comma fix
        lambda s: json.loads(re.sub(r",\s*([\]}])", r"\1",
                         re.sub(r"^```(?:json)?\s*\n?", "", re.sub(r"\n```\s*$", "", s.strip())))),
    ]

    for i, strategy in enumerate(strategies):
        try:
            result = strategy(raw)
            if isinstance(result, dict):
                return result
        except Exception:
            continue
    return None
