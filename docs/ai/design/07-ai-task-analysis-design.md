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
```json
{
  "quarter": "2026Q2",          // 可选，默认走 PersonalHours 配置
  "owner_key": "...",           // 可选，默认当前登录用户
  "project_ids": ["..."]        // 可选
}
```

**返回格式（完整规范）:**

```json
{
  "tasks": [
    {
      "taskId": "65af3615bab69f87ae8883b0",
      "title": "任务标题",
      "status": "已完成 | 未完成 | 创建中 | 待评审 | 评审中 | 搁置",
      "taskNature": "指派型 | 自主型 | 能力型 | 无",
      "type": "产品 | 研发 | 订单 | 无",
      "workHour": 2.5,
      "isOverdue": false,
      "dueDate": "2026-05-31"
    }
  ],
  "stats": {
    "quarter": "2026-04-01 ~ 2026-06-30",
    "total_tasks": 53,
    "done_count": 35,
    "overdue_count": 2,
    "total_work_hours": 41.4,
    "completed_work_hours": 34.9,
    "quarter_work_hour": 41.4,
    "quarter_completed_work_hour": 34.9,
    "quarter_overdue_work_hour": 0.0,
    "filled_cost_hour_sum": 12.3,
    "assigned_pct": 35.8,
    "autonomous_pct": 11.3,
    "capability_pct": 0.0,
    "coefficient": 0.4,
    "workday_count": 121,
    "expected_effective_days": 48.4,
    "passed_workdays": 118,
    "expected_hours_by_today": 47.2
  }
}
```

**字段说明:**

| 字段 | 含义 | 来源 |
|------|------|------|
| tasks[].status | 任务状态 | task_flow_status_id → 中文映射 |
| tasks[].taskNature | 工时类型 | 钉钉自定义字段 ID → 中文映射 |
| tasks[].type | 业务类型 | business_type → 产品/研发/订单 |
| stats.quarter_work_hour | 已排总有效工时 | executor_quarter_workhours |
| stats.quarter_completed_work_hour | 已完成有效工时 | 同上 |
| stats.quarter_overdue_work_hour | 逾期总工时 | 同上 |
| stats.filled_cost_hour_sum | 工作日耗时已填写 | 同上 |
| stats.workday_count | 实际工作日数 | Chinese calendar |
| stats.expected_effective_days | 预期有效工时 | workday_count × coefficient |
| stats.passed_workdays | 到今天已过工作日 | 同上 |
| stats.assigned_pct | 指派型占比 | task_nature 统计 |
| stats.autonomous_pct | 自主型占比 | 同上 |
| stats.capability_pct | 能力型占比 | 同上 |

**数据源:**
- 工时数据 → `executor_quarter_workhours_db_service`（与 PersonalHours 同一数据源）
- 映射表 → `TASK_NATURE_VALUE_ID_TO_CODE` / `TASK_FLOW_STATUS_TO_LABEL` / `BUSINESS_TYPE_TO_LABEL`（与前端 realQueryPersonalHours 一致）
- 工作日 → `workdays_in_range_service` + `chinese_calendar`
- 系数 → `get_workhour_character_coefficients_service`

### 4.2 步骤 2: 知识库检索

`POST /api/bt/ai/task-analysis/search-kb`

入参:
```json
{
  "keywords": "导航优化 托盘识别",   // 手动指定
  "tasks": [...],                   // 步骤1返回的任务列表
  "generate": true,                 // true=自动生成，false=用 keywords
  "top_k": 20
}
```

**关键词提取**（两条路）：

| 方案 | 做法 | 状态 |
|------|------|------|
| 简单拼接 | 取任务 title 拼接为搜索字符串 | ✅ 当前 |
| LLM 提取 | 调 LLM 从任务列表提取 10-15 个技术关键词 | ⏸ 待调通 |

> deepseek-v4-flash / MiniMax-M2.7 返回 `reasoning_content` 但 `content` 为空，关键词无法提取。当前默认用 title 拼接，`search_hybrid` 语义检索能兜底。

返回:
```json
{
  "chunks": [
    {"chunkId": 265, "source": "todo list.adoc", "content": "...", "score": 0.0304}
  ],
  "search_query": "导航优化 托盘识别"
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
