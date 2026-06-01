"""Task analysis report: construct prompt + call LLM for multi-dimensional analysis."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

import requests

logger = logging.getLogger(__name__)

_PROMPT_TEMPLATE = """你是企业内部任务分析助手。请基于以下任务数据和知识库参考资料，对任务进行多维度分析。

## 任务数据
- 标题：{title}
- 项目ID：{project_id}
- 执行人：{executor_id}
- 优先级：{priority}
- 进度：{progress}%
- 状态：{status}
- 是否逾期：{is_overdue}
- 截止日期：{due_date}
- 工时：{work_hour}人天
- 任务类型：{task_nature}
- 业务类型：{business_type}
- 备注：{note}

## 知识库参考资料
{knowledge_context}

## 分析要求
请从以下维度对任务进行分析，用 JSON 格式返回（不要包含 markdown 代码块标记）：

1. **任务完整性评估** (completeness)：标题是否清晰、需求描述是否充分、产出是否明确、时间安排是否合理
2. **风险识别** (risks)：逾期风险、信息缺失风险、资源冲突等，每个风险包含 level(high/medium/low) 和 description
3. **知识库合规性** (compliance)：任务是否符合知识库中记录的相关规范、流程、最佳实践
4. **改进建议** (suggestions)：基于知识库参考资料，给出具体可操作的改进建议，每条建议引用对应的知识库来源

返回格式：
{{
  "completeness": {{
    "score": "good / fair / poor",
    "detail": "评估说明"
  }},
  "risks": [
    {{"level": "high/medium/low", "description": "具体风险"}}
  ],
  "compliance": {{
    "score": "good / fair / poor / unknown",
    "detail": "与知识库规范的对照说明"
  }},
  "suggestions": [
    {{"action": "建议内容", "reference": "引用知识库文档名称"}}
  ],
  "summary": "一句话总结"
}}

只返回 JSON，不要其他内容。"""


def _load_config() -> dict:
    config_path = __file__.replace("/analyze.py", "/../config.json")
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


def analyze_task_report(task: Dict[str, Any], knowledge: List[Dict[str, Any]]) -> dict:
    """Generate a multi-dimensional analysis report for a task.

    Args:
        task: Task summary dict from analyze/task endpoint.
        knowledge: List of KB chunk dicts with source, content, score.

    Returns:
        Parsed analysis report dict, or {"error": "..."} on failure.
    """
    # Build knowledge context
    kb_parts: list[str] = []
    for i, k in enumerate(knowledge[:6]):  # limit to top 6 to control prompt length
        source = k.get("source", "未知文档")
        content = k.get("content", "")
        # Truncate very long chunks
        if len(content) > 1200:
            content = content[:1200] + "..."
        kb_parts.append(f"[参考{i+1}: {source}]\n{content}")

    knowledge_context = "\n\n---\n\n".join(kb_parts) if kb_parts else "无相关参考资料"

    # Build prompt
    business_type_map = {0: "产品", 1: "研发", 2: "订单"}
    status_parts = []
    if task.get("isDone"):
        status_parts.append("已完成")
    else:
        status_parts.append("进行中")
    if task.get("isOverdue"):
        status_parts.append("已逾期")

    prompt = _PROMPT_TEMPLATE.format(
        title=task.get("title", ""),
        project_id=task.get("projectId", ""),
        executor_id=task.get("executorId", ""),
        priority=task.get("priority", 0),
        progress=task.get("progress", 0),
        status=", ".join(status_parts) if status_parts else "未知",
        is_overdue="是" if task.get("isOverdue") else "否",
        due_date=task.get("dueDate") or "未设置",
        work_hour=task.get("workHour") or "未填写",
        task_nature=task.get("taskNature") or "未分类",
        business_type=business_type_map.get(task.get("businessType"), "未知"),
        note=task.get("note") or "无",
        knowledge_context=knowledge_context,
    )

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
                    {"role": "system", "content": "你是一个专业的任务分析助手，总是用 JSON 格式回答。"},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.2,
                "max_tokens": 2048,
            },
            timeout=90,
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

        # Parse JSON from response (strip possible markdown fences)
        content = content.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:]) if len(lines) > 1 else content
        if content.endswith("```"):
            content = content[: content.rfind("```")].strip()

        return json.loads(content)

    except requests.RequestException as e:
        logger.exception("LLM request failed")
        return {"error": f"LLM 调用失败: {str(e)}"}
    except json.JSONDecodeError as e:
        logger.error("LLM returned invalid JSON: %s", str(e))
        return {"error": "LLM 返回格式异常，请重试", "raw": content[:500]}
