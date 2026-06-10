"""步骤3: Prompt 构造 + LLM 调用，生成 4 模块分析报告。

Prompt 模板从 ai/skills/1_tb_analysis/SKILL.md 读取。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List

import requests

logger = logging.getLogger(__name__)

_SKILL_PATH = (
    Path(__file__).resolve().parent.parent / "skills" / "1_tb_analysis" / "SKILL.md"
)


def _load_prompt() -> str:
    raw = _SKILL_PATH.read_text(encoding="utf-8")
    if raw.startswith("---"):
        end = raw.find("---", 3)
        if end != -1:
            raw = raw[end + 3:]
    return raw.strip()


def _load_config() -> dict:
    config_path = __file__.replace("/task_analysis/analysis.py", "/config.json")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _llm_call(messages: list, max_tokens: int = 16384) -> str:
    cfg = _load_config()
    base = str(cfg.get("base_url", "")).strip().rstrip("/")
    api_key = str(cfg.get("api_key", "")).strip()
    model = str(cfg.get("model", "MiniMax-M2.7")).strip()

    resp = requests.post(
        f"{base}/v1/chat/completions",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        json={"model": model, "messages": messages, "temperature": 0.2, "max_tokens": max_tokens},
        timeout=120,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"].get("content", "")
    # fallback to reasoning_content if content is empty (deepseek models)
    if not content:
        content = resp.json()["choices"][0]["message"].get("reasoning_content", "")
    return content.strip()


def _fix_truncated_json(text: str) -> str | None:
    """尝试修复被截断的 JSON，补上缺失的括号."""
    text = text.strip()
    open_braces = text.count("{") - text.count("}")
    open_brackets = text.count("[") - text.count("]")
    if open_braces <= 0 and open_brackets <= 0:
        return None
    last_newline = text.rfind("\n")
    if last_newline > 0:
        text = text[:last_newline]
    return text + "]" * open_brackets + "}" * open_braces


def _call_and_parse(prompt: str, label: str, max_tokens: int = 16384) -> dict:
    """调 LLM 并解析 JSON."""
    try:
        content = _llm_call([
            {"role": "system", "content": "严格按 JSON 格式回答，不要加 markdown 代码块或任何解释。"},
            {"role": "user", "content": prompt},
        ], max_tokens=max_tokens)
        if not content:
            return {"error": f"{label}: LLM 返回空内容"}

        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:])
        if content.endswith("```"):
            content = content[: content.rfind("```")].strip()

        result = json.loads(content)
        return result
    except json.JSONDecodeError:
        fixed = _fix_truncated_json(content)
        if fixed:
            try:
                return json.loads(fixed)
            except json.JSONDecodeError:
                pass
        logger.error(f"{label}: JSON parse failed")
        return {"error": f"{label}: LLM 返回格式异常", "raw": (content or "")[:300]}


def _build_quarter_summary(stats: dict) -> str:
    return (
        f"季度:{stats.get('quarter', '?')}, 工作日:{stats.get('workday_count', 0)}d, "
        f"系数:{stats.get('coefficient', 1.0)}, "
        f"预期有效:{stats.get('expected_effective_days', 0)}d, "
        f"已过:{stats.get('passed_workdays', 0)}d"
    )


def _build_status_breakdown(stats: dict) -> str:
    sb = stats.get("statusBreakdown", {})
    lines = [f"  {k}: {v['count']}条/{v['hours']}d({v.get('pct',0)}%)" for k, v in sb.items()]
    return "\n".join(lines) if lines else "无"


def _build_nature_distribution(stats: dict) -> str:
    nb = stats.get("natureDistribution", {})
    lines = [f"  {k}: {v['count']}条/{v['hours']}d({v.get('pct',0)}%)" for k, v in nb.items()]
    return "\n".join(lines) if lines else "无"


def _build_task_distribution(stats: dict) -> str:
    tb = stats.get("taskDistribution", {})
    return ", ".join(f"{k}:{v}d" for k, v in tb.items()) if tb else "无"


def _build_expected_vs_actual(stats: dict) -> str:
    expected = stats.get("expected_effective_days", 0)
    actual = stats.get("quarter_work_hour", 0)
    completed = stats.get("quarter_completed_work_hour", 0)
    expected_by_today = stats.get("expected_hours_by_today", 0)
    return (
        f"预期有效:{expected}d, 所需:{expected_by_today}d, "
        f"已排:{actual}d, 已完成:{completed}d, "
        f"缺口:{round(expected - actual, 1)}d, 所需缺口:{round(expected_by_today - completed, 1)}d"
    )


def generate_report(
    tasks: List[Dict[str, Any]],
    stats: Dict[str, Any],
    chunks: List[Dict[str, Any]],
) -> dict:
    """生成 6 模块分析报告。分两次 LLM 调用，避免输出截断。

    调用1: 需求雷达 + 技术债审计师 + 绩效平衡仪
    调用2: 成长助推器 + 效能转化器 + 风险预警机
    """
    # 任务上下文
    task_lines = []
    for t in tasks[:20]:
        parts = [f"- [{t.get('taskNature', '?')}] {t.get('title', '')}"]
        parts.append(f"  状态:{t.get('status', '?')} 工时:{t.get('workHour', 0)}d")
        desc = t.get('description', '')
        if desc:
            parts.append(f"  描述:{desc[:200]}")
        outputs = t.get('outputs', '')
        if outputs:
            parts.append(f"  产出:{outputs[:200]}")
        sibs = t.get('siblings', [])
        if sibs:
            sib_titles = [s['title'] for s in sibs[:5]]
            parts.append(f"  兄弟任务: {' | '.join(sib_titles)}")
        task_lines.append("\n".join(parts))
    task_context = "\n".join(task_lines) if task_lines else "无"

    # 知识库上下文
    kb_parts = []
    for i, c in enumerate(chunks[:6]):
        content = c.get("content", "")
        if len(content) > 800:
            content = content[:800] + "..."
        kb_parts.append(f"[{i + 1}: {c.get('source', '?')}]\n{content}")
    kb_context = "\n\n---\n\n".join(kb_parts) if kb_parts else "无"

    # 工时统计
    work_hour_stats = (
        f"总任务:{stats.get('total_tasks', 0)}, 完成:{stats.get('done_count', 0)}, "
        f"逾期:{stats.get('overdue_count', 0)}, "
        f"已排:{stats.get('quarter_work_hour', 0)}d, 完成:{stats.get('quarter_completed_work_hour', 0)}d"
    )
    ratio_stats = (
        f"指派:{stats.get('assigned_pct', 0)}%, "
        f"自主:{stats.get('autonomous_pct', 0)}%, "
        f"能力:{stats.get('capability_pct', 0)}%"
    )

    # 组装上下文（两次调用共用）
    ctx = {
        "task_context": task_context,
        "work_hour_stats": work_hour_stats,
        "quarter_summary": _build_quarter_summary(stats),
        "status_breakdown": _build_status_breakdown(stats),
        "nature_distribution": _build_nature_distribution(stats),
        "task_distribution": _build_task_distribution(stats),
        "expected_vs_actual": _build_expected_vs_actual(stats),
        "kb_context": kb_context,
        "ratio_stats": ratio_stats,
        "overdue_count": str(stats.get("overdue_count", 0)),
        "overdue_hours": str(stats.get("quarter_overdue_work_hour", 0)),
    }

    full_prompt = _load_prompt()
    for k, v in ctx.items():
        full_prompt = full_prompt.replace("{" + k + "}", v)

    # 拆分为两组 prompt
    group_1_end = full_prompt.find("### 4. 任务分布与风险分析")
    group_1_prompt = (
        full_prompt[:group_1_end] + "\n\n"
        '只输出 JSON：{"requirement_radar": {...}, "autonomous_suggestions": {...}, "capability_suggestions": {...}}\n'
        "不要 markdown 代码块。"
    )
    group_2_start = full_prompt.find("### 4. 任务分布与风险分析")
    group_2_prompt = (
        full_prompt[group_2_start:] + "\n\n"
        '只输出 JSON：{"task_risk_analysis": {...}}\n'
        "不要 markdown 代码块。"
    )

    # 两次 LLM 调用 — group1 需要更多 token（12+12 条建议 + 需求雷达）
    r1 = _call_and_parse(group_1_prompt, "group1", max_tokens=32768)
    r2 = _call_and_parse(group_2_prompt, "group2")

    if "error" in r1 and "error" in r2:
        return {"error": f"group1: {r1.get('error')}; group2: {r2.get('error')}"}

    merged = {**r1, **r2}
    for m in ["requirement_radar", "autonomous_suggestions", "capability_suggestions",
              "task_risk_analysis"]:
        if m not in merged:
            merged[m] = {}

    # 补调：如果自主型/能力型建议为空，单独 LLM 调用一次
    def _is_empty_suggestions(mod: dict) -> bool:
        if not isinstance(mod, dict):
            return True
        sug = mod.get("suggestions")
        return not isinstance(sug, list) or len(sug) == 0

    def _retry_module(module_id: int, next_id: int, output_key: str, sample_json: str) -> dict | None:
        start_marker = f"### {module_id}."
        end_marker = f"### {next_id}."
        start = full_prompt.find(start_marker)
        if start == -1:
            return None
        end = full_prompt.find(end_marker, start)
        section = full_prompt[start:end] if end != -1 else full_prompt[start:]
        prompt = section + "\n\n只输出 JSON：" + sample_json + "\n不要 markdown 代码块。"
        result = _call_and_parse(prompt, f"module{module_id}_retry", max_tokens=32768)
        if output_key in result:
            return result[output_key]
        if "suggestions" in result:
            return result
        return None

    if _is_empty_suggestions(merged.get("autonomous_suggestions")):
        logger.warning("autonomous_suggestions empty, retrying individually...")
        retry = _retry_module(2, 3, "autonomous_suggestions",
            '{"suggestions": [{"source_task": "任务标题", "problem": "发现的问题", "action": "改进建议", "priority_score": 8, "effort_days": 1.5, "task_template": {"title": "任务标题", "requirement_desc": "需求描述", "outputs": ["产出描述1(0.5天)", "产出描述2(1.0天)"]}}]}')
        if retry:
            merged["autonomous_suggestions"] = retry
            logger.info("autonomous_suggestions retry OK, %d items", len(retry.get("suggestions", [])))
        else:
            logger.error("autonomous_suggestions retry FAILED")

    if _is_empty_suggestions(merged.get("capability_suggestions")):
        logger.warning("capability_suggestions empty, retrying individually...")
        retry = _retry_module(3, 4, "capability_suggestions",
            '{"suggestions": [{"direction": "学习方向", "reason": "为什么需要学", "output_required": "强制产出", "priority_score": 8, "effort_days": 1.5, "task_template": {"title": "任务标题", "requirement_desc": "需求描述", "outputs": ["产出描述1(0.5天)", "产出描述2(1.0天)"]}}]}')
        if retry:
            merged["capability_suggestions"] = retry
            logger.info("capability_suggestions retry OK, %d items", len(retry.get("suggestions", [])))
        else:
            logger.error("capability_suggestions retry FAILED")

    return merged
