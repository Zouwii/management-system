# AI 任务分析栏设计

> 最后更新: 2026-06-01

## 1. 目标

在 AI 助理页面提供一个多维度任务分析面板，拉取用户 TB 任务数据、结合知识库规范文档，生成结构化分析报告。

## 2. 拆分前（现状）

单体 API `POST /ai/knowledge/analyze/dashboard`，一次请求完成所有处理：

```
查 TB（30条） → 统计工时 → 搜知识库 → LLM 分析 → 返回 6 模块
```

问题：
- 黑盒，中间过程不可见
- 搜索词自动生成，不可调整
- 按 priority 取 30 条，不按季度过滤
- 前端无法交互控制每步结果

## 3. 拆分后架构

模块路径: `ai/task_analysis/`

```
ai/task_analysis/
├── __init__.py        # register(bp, ok, fail)
├── routes.py          # 3 个端点
├── data.py            # 步骤1: TB 数据查询 + 工时统计
├── retrieval.py       # 步骤2: 知识库检索
└── analysis.py        # 步骤3: prompt 构造 + LLM 调用
```

前端调用流程：

```
步骤1: POST /api/bt/ai/task-analysis/fetch-tasks
  → 返回 { tasks, stats }
  → 前端展示任务清单和工时统计

步骤2: POST /api/bt/ai/task-analysis/search-kb
  → 返回 { chunks, search_query }
  → 前端可修改 keywords 重新检索

步骤3: POST /api/bt/ai/task-analysis/generate-report
  → 返回 { modules }
  → 前端渲染 6 模块卡片
```

## 4. 端点设计

### 4.1 步骤 1: 拉取任务数据

`POST /api/bt/ai/task-analysis/fetch-tasks`

入参:
```
{
  quarter?: "2026Q2",         // 默认当前季度
  owner_key?: "...",          // 默认当前登录用户
  project_ids?: ["..."]       // 可选，限定项目
}
```

返回:
```
{
  tasks: [
    { taskId, title, progress, isOverdue, isDone, workHour, taskNature, dueDate }
  ],
  stats: {
    total_tasks, done_count, overdue_count, total_work_hours,
    assigned_pct, autonomous_pct, capability_pct
  }
}
```

### 4.2 步骤 2: 知识库检索

`POST /api/bt/ai/task-analysis/search-kb`

入参:
```
{
  keywords: "导航优化 托盘识别",   // 前端可手动编辑
  top_k: 20                       // 默认 20
}
```

返回:
```
{
  chunks: [
    { chunk_id, title, content, score }
  ],
  search_query: "导航优化 托盘识别"
}
```

### 4.3 步骤 3: 生成分析报告

`POST /api/bt/ai/task-analysis/generate-report`

入参:
```
{
  tasks: [...],     // 来自步骤1
  stats: {...},     // 来自步骤1
  chunks: [...]     // 来自步骤2
}
```

返回:
```
{
  modules: {
    requirement_radar: { keywords: [...] },
    tech_debt_auditor: { gaps: [...], summary: "..." },
    performance_balancer: { ratio: {...}, status: "...", suggestions: [...] },
    growth_booster: { learnings: [...] },
    efficiency_transformer: { tools: [...] },
    risk_warning_engine: { alerts: [...], draft_tasks: [...] }
  }
}
```

Prompt 模板从 `runtime/shared/.claude/skills/task-analysis/SKILL.md` 读取，占位符用 `str.replace()` 填充，避免 JSON 花括号冲突。

## 5. 前端改造

"AI 任务分析栏"折叠块内的交互改为 3 步：

```
[开始分析]
  ↓ 调 fetch-tasks → 展示任务清单 + 工时统计
[检索知识库]
  ← 前端可编辑关键词，调 search-kb → 展示搜索结果
[生成报告]
  ↓ 调 generate-report → 6 模块卡片渲染
```

## 6. 清理

从 `ai/knowledge/routes.py` 删除:
- `/analyze/dashboard`
- `/analyze/task`
- `/analyze/task/report`

从 `ai/__init__.py` 注册 `_register_task_analysis(bp, ok, fail)`。

从 `ai/knowledge/` 删除:
- `dashboard_analysis.py`（逻辑迁至 `task_analysis/analysis.py`）
- `analyze.py`（逻辑迁至 `task_analysis/routes.py`）
