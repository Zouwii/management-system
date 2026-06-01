"""AI 任务分析栏 — 3 步拆分的任务分析模块。

步骤:
  1. POST /ai/task-analysis/fetch-tasks      — TB 数据查询 + 工时统计
  2. POST /ai/task-analysis/search-kb        — 知识库检索
  3. POST /ai/task-analysis/generate-report  — Prompt + LLM 生成报告
"""

from ai.task_analysis.routes import register as _register_routes


def register(bp, ok, fail):
    _register_routes(bp, ok, fail)
