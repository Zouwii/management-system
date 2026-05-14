# ai-tbcreate 模块设计文档

## 概述

`ai-tbcreate` 是 AI Teambition 任务创建的完整流水线。用户在前端左侧 ttyd 终端中与 Claude CLI 自然对话，Claude 根据工作区中的上下文文件和规则文件理解用户需求，将任务草稿写入 `draft.json`。后端读取该文件供前端右侧面板轮询显示，用户确认后调用钉钉 API 创建 Teambition 任务。

## 架构

```
┌─ 浏览器 ─────────────────────────────────────────────────┐
│  左侧: ttyd iframe               右侧: 草稿面板            │
│  ┌──────────────────────────┐   ┌────────────────────┐   │za
│  │ Claude CLI               │   │ 标题: xxx          │   │
│  │ 读取:                    │   │ 类型: 开发实现      │   │
│  │  - CLAUDE.md             │   │ 工时: 指派型        │   │
│  │  - AI_TASK_CONTEXT.md    │   │ 需求: xxx          │   │
│  │  - TASK_TICKET_RULES.md  │   │ 产出: [a, b]       │   │
│  │                          │   │ 参与度: 1.5 人天    │   │
│  │ 写入: draft.json ────────┼──→│                    │   │
│  └──────────────────────────┘   │ [创建 TB 任务单]   │   │
│                                 └────────────────────┘   │
│        ▲ ttyd WebSocket           ▲ GET /draft/current   │
│        │                          │ 轮询 (2s)            │
└────────┼──────────────────────────┼──────────────────────┘
         │                          │
   ┌─────┴──────────────────────────┴──────┐
   │            Flask 后端                   │
   │                                         │
   │  ai/terminal/session.py                │
   │    - ttyd 进程管理                      │
   │    - 端口分配                           │
   │    - 工作区准备 (CLAUDE.md +            │
   │      AI_TASK_CONTEXT.md +               │
   │      TASK_TICKET_RULES.md)              │
   │                                         │
   │  ai/tbcreate/routes.py                  │
   │    GET /ai/tbcreate/draft/current       │
   │    - 读 workspace/draft.json            │
   │    - 返回 JSON                           │
   │                                         │
   │  ai/mission/service.py                  │
   │    - build_ai_mission_create_payload()  │
   │    - ai_create_mission_service()        │
   │    - 调钉钉 API 创建任务                  │
   └─────────────────────────────────────────┘
```

## 数据流

```
1. 用户打开 AI 助理页
   → POST /api/bt/ai/ttyd/session
   → backend: ensure_ttyd_session()
        → make_env() 读取 ai/config.json
        → write_workspace_context()
            → 写 CLAUDE.md（含 draft.json 规范）
            → 写 AI_TASK_CONTEXT.md（用户 DB 任务上下文）
            → 复制 ai/rules/task_ticket.md → TASK_TICKET_RULES.md
        → 启动 ttyd → launcher.sh → claude CLI
   → 返回 embedUrl，前端渲染 ttyd iframe

2. 用户在终端中与 Claude 对话
   → Claude 读取 CLAUDE.md → 理解工作流程
   → Claude 读取 AI_TASK_CONTEXT.md → 理解用户历史任务
   → Claude 读取 TASK_TICKET_RULES.md → 理解字段规则
   → 对话收集需求
   → 用户确认后，Claude 写 draft.json 到当前目录 (workspace/default/)

3. 前端轮询 draft
   → GET /api/bt/ai/tbcreate/draft/current?ownerKey=xxx (每 2s)
   → backend: resolve_owner_key() → user_workspace() → 读 draft.json
   → 返回 JSON → normalizeDraft() → 更新右侧面板

4. 用户点"创建 Teambition 任务单"
   → POST /api/dashboard/ai-task-ticket
   → ai_create_mission_service()
        → build_ai_mission_create_payload(draft)
        → POST DingTalk API
        → 返回 taskId + taskUrl
```

## 工作区文件

每次用户创建 ttyd session 时，`write_workspace_context()` 在工作区生成三个文件：

| 文件 | 内容 | 来源 |
|------|------|------|
| `CLAUDE.md` | 工作流程指令 + `draft.json` 字段规范 | `session.py` 内联模板 |
| `AI_TASK_CONTEXT.md` | 用户历史任务上下文（DB 读取，最多 80 条） | `tbcreate/context.py` |
| `TASK_TICKET_RULES.md` | 任务单字段判断规则 | 复制自 `ai/rules/task_ticket.md` |

路径：`runtime/users/<sha256(ownerKey)>/workspaces/default/`

## draft.json 格式

```json
{
  "title": "任务标题",
  "taskType": "方案设计任务 | 开发实现任务 | 系统联调任务",
  "workType": "指派型 | 自主型 | 能力建设型",
  "requirementDesc": "需求描述",
  "outputs": ["产出1", "产出2"],
  "participationLevel": 0.2 | 0.5 | 1 | 1.5 | 2 | 2.5 | 3,
  "dueDate": "2026-05-30T00:00:00Z",
  "startDate": "2026-05-14T00:00:00Z"
}
```

## API 端点

### tbcreate

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/bt/ai/tbcreate/workspace/init` | **显式初始化工作区**。写入 CLAUDE.md + AI_TASK_CONTEXT.md + TASK_TICKET_RULES.md |
| GET | `/api/bt/ai/tbcreate/draft/current?ownerKey=` | 读取工作区 draft.json，返回 JSON。文件不存在时返回空草稿 |

### terminal（不变）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/bt/ai/models` | 列出可用模型 |
| POST | `/api/bt/ai/ttyd/session` | 创建 ttyd 会话 |

### mission（不变）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/bt/ai/create_mission/payload` | 调试：预览钉钉 API payload |
| POST | `/api/bt/ai/create_mission` | 创建 Teambition 任务 |

### dashboard（不变）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/dashboard/ai-task-ticket` | 前端创建任务入口，调用 mission service |

## 模块依赖

```
ai/__init__.py
  ├── ai/tbcreate/routes.py ────→ ai/terminal/session.py (user_workspace, resolve_owner_key)
  ├── ai/mission/routes.py ─────→ ai/mission/service.py (DingTalk API)
  └── ai/terminal/routes.py ────→ ai/terminal/session.py (ttyd lifecycle)
                                      │
                                      └──→ ai/tbcreate/context.py (write_user_task_context_markdown)
```

无循环依赖。`context.py` 只依赖 `db/` 和标准库。

## 与旧版 task_assistant 的对比

| | 旧 task_assistant | 新 tbcreate |
|---|---|---|
| AI 引擎 | 正则关键词匹配 | Claude CLI (真实 LLM) |
| 对话方式 | 文本输入框 + 固定回复模板 | ttyd 终端内自然对话 |
| 草稿生成 | `_merge_draft()` 正则推断 | Claude 写 `draft.json` |
| 草稿获取 | conversation JSON 内嵌 | 文件系统轮询 |
| 上下文 | 内联 contextSummary | 文件系统 (CLAUDE.md + AI_TASK_CONTEXT.md) |
| 规则注入 | 无 | TASK_TICKET_RULES.md |
| HTTP 端点 | 4 个 (CRUD conversations) | 1 个 (draft polling) |
| Skill/文件操作 | 不支持 | Claude CLI 原生支持 |

## 前端页面结构

`AIAnalysisPage.jsx`：

```
┌─ AI任务分析栏 ──────────────────────────────┐
│  工时分析卡片  │  绩效分析卡片                │
└──────────────────────────────────────────────┘

┌─ AI创建任务单 ──────────────────────────────┐
│  模型: xxx                   草稿状态: xxx   │
│  ┌──────────────┬────────────────────────┐  │
│  │ AI 终端       │ 右侧草稿面板            │  │
│  │ (ttyd iframe) │  - 标题                │  │
│  │              │  - 类型 (select)        │  │
│  │ 全高度终端    │  - 工时类型 (select)     │  │
│  │ Claude CLI   │  - 需求描述             │  │
│  │ 自然对话      │  - 产出列表             │  │
│  │              │  - 参与度 (select)       │  │
│  │              │  - [创建 TB 任务单]      │  │
│  └──────────────┴────────────────────────┘  │
└──────────────────────────────────────────────┘
```

右侧面板每 2 秒轮询一次 draft.json，Claude 写入后自动刷新。用户可在右侧修改字段后创建任务。
