"""绩效达标分析：Python 预计算档位差距（按绩效公式使用结余），LLM 做排单建议。"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List

import requests

logger = logging.getLogger(__name__)

_SKILL_PATH = (
    Path(__file__).resolve().parent.parent / "skills" / "2_perf_analysis" / "SKILL.md"
)

# 档位定义: (下限, 上限, 标签, 公司分)，从高到低
_TIER_DEFS = [
    (1.5, 2.0, "1.5 (卓越)", 4.5),
    (1.2, 1.5, "1.2 (优秀)", 3.75),
    (1.0, 1.2, "1.0 (良好)", 3.5),
    (0.8, 1.0, "0.8 (标准)", 3.25),
    (0.0, 0.8, "0.5 (保底)", 3.0),
]


def _load_prompt() -> str:
    raw = _SKILL_PATH.read_text(encoding="utf-8")
    if raw.startswith("---"):
        end = raw.find("---", 3)
        if end != -1:
            raw = raw[end + 3:]
    return raw.strip()


def _load_config() -> dict:
    config_path = Path(__file__).resolve().parent.parent / "config.json"
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _llm_call(messages: list, max_tokens: int = 16384) -> str:
    cfg = _load_config()
    base = str(cfg.get("base_url", "")).strip().rstrip("/")
    api_key = str(cfg.get("api_key", "")).strip()
    model = str(cfg.get("model", "deepseek-v4-flash")).strip()
    resp = requests.post(
        f"{base}/v1/chat/completions",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        json={"model": model, "messages": messages, "temperature": 0.2, "max_tokens": max_tokens},
        timeout=180,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"].get("content", "")
    if not content:
        content = resp.json()["choices"][0]["message"].get("reasoning_content", "")
    return content.strip()


def _fix_truncated_json(text: str) -> str | None:
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
        return json.loads(content)
    except json.JSONDecodeError:
        fixed = _fix_truncated_json(content)
        if fixed:
            try:
                return json.loads(fixed)
            except json.JSONDecodeError:
                pass
        logger.error(f"{label}: JSON parse failed")
        return {"error": f"{label}: LLM 返回格式异常", "raw": (content or "")[:300]}


def _build_task_summary(tasks: List[dict], stats: dict) -> str:
    lines = []
    lines.append(
        f"总任务 {stats.get('total_tasks', 0)} 个，"
        f"已完成 {stats.get('done_count', 0)} 个，"
        f"逾期 {stats.get('overdue_count', 0)} 个"
    )
    nd = stats.get("natureDistribution", {})
    if nd:
        parts = [f"{k}: {v.get('count', 0)}条/{v.get('hours', 0)}d" for k, v in nd.items()]
        lines.append("性质分布: " + "，".join(parts))
    lines.append("（以下均为已排任务，已计入当前工时，不需要重复建议完成）")
    if tasks:
        lines.append("主要任务:")
        for t in tasks[:15]:
            nature = t.get("taskNature", "?")
            status = t.get("status", "?")
            wh = t.get("workHour", 0)
            title = (t.get("title") or "")[:40]
            overdue = " ⚠️逾期" if t.get("isOverdue") else ""
            lines.append(f"  [{nature}][{status}] {title} ({wh}d){overdue}")
    return "\n".join(lines)


def _calc_tier_table(prev_carry: float, planned: float, expected_days: float, remaining_days: float) -> dict:
    """按绩效公式预计算所有档位差距。

    绩效规则（来自 performance/service.py）：
    - overall 落在 [lower, upper) 区间
    - compensation = overall - upper
    - 若 prev_carry + compensation >= 0，升档到 upper；否则降档到 lower

    因此携带 carry 到达某档位 X (即 final_score = X) 的条件：
    - 需要 overall 落在 [X 的前一档下限, X) 区间内
    - 且 prev_carry + (overall - X) >= 0 → overall >= X - prev_carry
    - 综合：effective_lower = max(前一档下限, X - prev_carry)

    对于最低档(0.8)，前一档视为 [0, 0.8)。
    """
    work_hour_score = planned / max(expected_days, 0.01)

    tiers = []
    for i, (lower, upper, label, company_score) in enumerate(_TIER_DEFS):
        # 纯工时达标：需要排 lower * expected_days（进入此档区间）
        need_raw = round(lower * expected_days, 1)
        gap_raw = round(max(0, need_raw - planned), 1)

        # carry 修正：到达当前档位 X(=lower) 的最终绩效
        # 需要 overall ∈ [前一档下界, X)，且 carry 弥补 (X - overall)
        # 即 overall ≥ X - prev_carry 且 overall ≥ 前一档下界
        # → effective = max(前一档下界, X - prev_carry)
        #
        # 例：到达 1.5 档 → 前一档下界=1.2, X=1.5
        #   effective = max(1.2, 1.5-0.3) = max(1.2, 1.2) = 1.2 → carry 帮省 0.3 分 = 13.9d
        if i + 1 < len(_TIER_DEFS):
            prev_lower = _TIER_DEFS[i + 1][0]  # 前一档的 lower
        else:
            prev_lower = 0.0

        # 需要 overall >= X - prev_carry 才能用 carry 升到 X
        # X = upper (因为 final_score 升到 upper)
        carry_threshold = lower - prev_carry  # X - prev_carry
        effective_lower = max(prev_lower, carry_threshold)
        need_carry = round(effective_lower * expected_days, 1)
        gap_carry = round(max(0, need_carry - planned), 1)
        carry_saves = round(max(0, gap_raw - gap_carry), 1)

        already = planned >= need_raw or lower == 0.0
        reachable = gap_raw <= remaining_days or (carry_saves > 0 and gap_carry <= remaining_days)

        # 状态描述
        if already and lower > 0:
            note = "✓ 已达标"
        elif already and lower == 0:
            note = "✓ 最低保障"
        elif carry_saves > 0:
            note = f"纯差 {gap_raw}d → 结余帮省 {carry_saves}d → 实差 {gap_carry}d"
        elif gap_raw <= remaining_days:
            note = f"还需 {gap_raw}d"
        else:
            note = f"缺口 {gap_raw}d（不可达）"

        tiers.append({
            "tier": label,
            "company_score": company_score,
            "need_hours": need_raw,
            "gap_days": gap_raw,
            "carry_saves": carry_saves,
            "with_carry_gap": gap_carry if carry_saves > 0 else None,
            "reachable": reachable,
            "note": note,
        })

    return {
        "current_score": round(work_hour_score, 2),
        "prev_carry": round(prev_carry, 3),
        "expected_days": round(expected_days, 1),
        "remaining_days": round(remaining_days, 0),
        "planned_hours": round(planned, 1),
        "tiers": tiers,
    }


def _build_status_summary(gap_data: dict) -> dict:
    """Python 直接生成达标现状文本，杜绝 LLM 幻觉。"""
    score = gap_data["current_score"]
    carry = gap_data["prev_carry"]
    planned = gap_data["planned_hours"]
    expected = gap_data["expected_days"]
    remaining = gap_data["remaining_days"]

    status_parts = [
        f"当前绩效{score}（已排{planned}d/预期有效{expected}d），上季结余{carry:.3f}，本季度剩余工作日{remaining:.0f}d"
    ]

    pending = [t for t in gap_data["tiers"] if t["gap_days"] > 0]
    pending.sort(key=lambda t: t["gap_days"])

    for t in pending[:3]:
        lower = float(t["tier"].split(" ")[0])  # 从 "1.2 (优秀)" 提取 1.2
        need_score = round(max(0, lower - score - carry), 3)
        need_days = round(need_score * expected, 1)

        if need_score > 0:
            status_parts.append(
                f"→ {t['tier']}档：需绩效 {lower} - {score} - {carry:.3f} = {need_score}，"
                f"折合 {need_days}d —— {'可达' if t['reachable'] else '本季来不及'}"
            )
        else:
            status_parts.append(f"→ {t['tier']}档：当前绩效已覆盖，无需额外排单")

    return {
        "status": status_parts,
        "current_score": score,
        "prev_carry": carry,
    }


def generate_performance_report(
    prev_carry: float,
    tasks: List[dict],
    stats: dict,
) -> dict:
    """生成绩效达标分析报告。Python 算数字，LLM 只出排单建议。"""
    workday_count = stats.get("workday_count", 0)
    expected_days = stats.get("expected_effective_days", 1)
    passed_days = stats.get("passed_workdays", 0)
    planned_hours = stats.get("quarter_work_hour", 0)
    remaining_days = max(0, round(workday_count - passed_days, 1))

    # 预计算
    gap_data = _calc_tier_table(prev_carry, planned_hours, expected_days, remaining_days)

    # 构建表格
    lines = [
        "| 档位 | 公司分 | 需排 | 纯缺口 | 结余帮省 | 修正后 | 状态 |",
        "|------|--------|------|--------|----------|--------|------|",
    ]
    for r in gap_data["tiers"]:
        carry_display = f"{r['carry_saves']}d" if r['carry_saves'] > 0 else "—"
        gap_display = f"{r['with_carry_gap']}d" if r['with_carry_gap'] is not None else (
            "✓" if "✓" in r['note'] else f"{r['gap_days']}d"
        )
        lines.append(
            f"| {r['tier']} | {r['company_score']} | {r['need_hours']}d | "
            f"{r['gap_days']}d | {carry_display} | {gap_display} | {r['note']} |"
        )
    tier_table = "\n".join(lines)

    # Python 生成 status，LLM 只做排单
    status_summary = _build_status_summary(gap_data)

    full_prompt = _load_prompt()
    full_prompt = full_prompt.replace("{tier_table}", tier_table)
    full_prompt = full_prompt.replace("{task_summary}", _build_task_summary(tasks, stats))

    result = _call_and_parse(full_prompt, "perf_scheduling", max_tokens=4096)

    if "error" in result:
        scheduling_advice = {}
    else:
        scheduling_advice = result

    return {
        "status_summary": status_summary,
        "scheduling_advice": scheduling_advice,
    }
