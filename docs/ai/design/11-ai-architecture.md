# AI 后端架构

> 更新日期: 2026-06-05

---

## 一、模块总览

```
app.py → base/app.py (Flask create_app)
  └── base/api.py  → Blueprint /api/bt
        └── base/route_registry/__init__.py
              └── ai/__init__.py  → 注册 5 个子模块
```

| 子模块 | 目录 | 端点数 | 职责 |
|--------|------|:---:|------|
| knowledge | `ai/knowledge/` | 14 | 知识库同步、浏览、检索、聊天、分析 |
| task_analysis | `ai/task_analysis/` | 3 | 任务分析栏（拉数据→检索→LLM报告） |
| tbcreate | `ai/tbcreate/` | 6 | AI 创建 TB 任务草稿 |
| terminal | `ai/terminal/` | 3 | ttyd 交互终端 |
| teambition | `ai/teambition/` | 1 | 正式创建 TB 单 |
| mcp | `ai/mcp/` | - | MCP Server（独立进程） |

---

## 二、分层架构

```
┌─────────────────────────────────────────────────────────┐
│                     HTTP 路由层                          │
│  ai/knowledge/routes.py    ai/task_analysis/routes.py   │
│  ai/tbcreate/routes.py     ai/terminal/routes.py        │
│  ai/teambition/routes.py   ai/mcp/server.py             │
├─────────────────────────────────────────────────────────┤
│                     服务 / 逻辑层                         │
│                                                         │
│  检索:  retriever.py      search_hybrid()               │
│         keyword(FTS) + vector(cosine) → RRF 融合        │
│                                                         │
│  分析:  analysis.py        generate_report()            │
│         dashboard_analysis.py  analyze_dashboard()      │
│         analyze.py         analyze_task_report()        │
│                                                         │
│  聊天:  chat.py            chat_stream()  SSE 流式       │
│         chat_session.py    会话管理                      │
│                                                         │
│  同步:  auto_sync.py       sync_all_and_embed()          │
│         routes.py           _sync_workspace()            │
│         chunker.py          chunk_document()             │
│         embedder.py         embed_chunks()               │
│         parser.py           parse_document()             │
│                                                         │
│  任务:  context.py          load_user_task_context()     │
│         workspace.py        init_workspace()             │
│         service.py          create_task()                │
│                                                         │
│  终端:  session.py          ensure_ttyd_session()        │
├─────────────────────────────────────────────────────────┤
│                      数据层                              │
│                                                         │
│  MySQL (tb_management)                                  │
│    kb_documents    知识库文档缓存                         │
│    kb_chunks       文档分块 (FULLTEXT 索引)               │
│    project_task    项目任务                              │
│    project_task_detail  任务详情                         │
│                                                         │
│  pgvector (kb_vectors)                                  │
│    chunk_vectors   分块向量 (cosine 语义搜索)             │
└─────────────────────────────────────────────────────────┘
```

---

## 三、外部依赖

| 依赖 | 地址 | 用途 | 调用方 |
|------|------|------|--------|
| 钉钉知识库 API | `api.dingtalk.com` | 同步文档内容 | knowledge/routes.py |
| 钉钉 TB API | `api.dingtalk.com` | 创建 Teambition 任务 | teambition/service.py |
| 钉钉 OAuth | `oapi.dingtalk.com` | 获取 access_token（缓存） | base/dingtalk_client.py |
| LLM API | `one-api.server22.jz` | 分析/聊天/报告 | analysis/chat/dashboard |
| 本地 Embedding | `BAAI/bge-small-zh-v1.5` | 语义向量（离线） | embedder.py |
| ttyd | 本地进程 | Web 终端代理 | terminal/session.py |
| claude CLI | 本地命令 | AI 交互终端 | terminal/launcher.sh |

---

## 四、核心数据流

### 4.1 知识库同步 → 检索

```
钉钉 API                         本地处理                     本地存储
───────                         ────────                    ────────
② list_nodes  ──→ 遍历目录树 ──→ 跳过 WORKBOOK
                  category=ALIDOC?
                    ↓ 是
④ get_blocks   ──→ parser → md ──→ kb_documents.content
                                      ↓
                               chunker → kb_chunks (FTS 索引)
                                      ↓
                               embedder → chunk_vectors (pgvector)
```

**同步模式：**

| | 小同步（每周一/四） | 大同步（每月1号） |
|------|------|------|
| 触发 | daemon 04:00 | daemon 04:00 |
| 逻辑 | 只拉未缓存的新 ALIDOC | 对比 `remote_modified_at`，重拉变更的 |
| 钉钉调用 | ~5,000 次 | ~5,000 + 少量 blocks |

### 4.2 语义检索

```
用户查询
   │
   ▼
search_hybrid(query)
   ├── search_chunks(query)    MySQL FULLTEXT  → keyword 结果 (top_k*2)
   └── search_vector(query)    pgvector cosine → vector 结果 (top_k*2)
          │
          ▼
   RRF 融合: score = Σ 1/(60 + rank_i)
          │
          ▼
   合并去重，按 RRF 总分降序 → top_k 条
```

### 4.3 AI 分析

```
POST /ai/task-analysis/fetch-tasks     → MySQL project_task
POST /ai/task-analysis/search-kb       → search_hybrid()
POST /ai/task-analysis/generate-report → LLM (2次调用, 各 max 16384 tokens)
                                         返回 4 模块 JSON 报告
```

```
POST /ai/knowledge/analyze/dashboard   → MySQL + search_hybrid + LLM (1次)
                                         返回 6 模块分析
```

```
GET  /ai/knowledge/chat                → search_hybrid + LLM SSE 流式
                                         多轮对话 + 会话历史
```

### 4.4 任务创建

```
前端填写草稿  ──→ draft.json (workspace 文件)
                    ↓
              claude CLI 通过 MCP tools 操作:
                get_user_task_context()  → MySQL
                save_task_draft()       → draft.json
                create_teambition_task() → 钉钉 TB API
```

---

## 五、后台任务

```
app.py 启动时启动 daemon 线程:

┌─ _auto_knowledge_sync_loop
│  每周一/四 04:00 → sync_all_and_embed(full_sync=False)
│  每月1号 04:00   → sync_all_and_embed(full_sync=True)
│
│  sync_all_and_embed():
│    Phase 1: sync    → 钉钉 API 拉文档
│    Phase 2: rechunk → MySQL 分块
│    Phase 3: embed   → pgvector 向量化
│
│  日志: runtime/logs/ai_sync_embed.log
│  钉钉调用日志: runtime/logs/ai_debug.log
│
└─ _auto_full_update_loop  (原有 TB 数据同步)
```

---

## 六、API 端点一览

| 方法 | 路径 | 功能 | 外部调用 |
|------|------|------|:---:|
| GET | `/api/bt/ai/knowledge/workspaces` | 知识库列表 | 钉钉 ① |
| GET | `/api/bt/ai/knowledge/workspaces/<id>/nodes` | 目录浏览 | 钉钉 ② |
| GET | `/api/bt/ai/knowledge/documents/<id>` | 文档内容 | 钉钉 ④ |
| POST | `/api/bt/ai/knowledge/sync` | 单库同步 | 钉钉 ①②④ |
| POST | `/api/bt/ai/knowledge/sync-all` | 全量同步 | 钉钉 ①②④ |
| POST | `/api/bt/ai/knowledge/sync-and-embedding` | 同步+分块+嵌入 | 钉钉+本地 |
| POST | `/api/bt/ai/knowledge/search` | 钉钉搜索 | 钉钉 ⑦⑧ |
| POST | `/api/bt/ai/knowledge/chunks/search` | 本地检索 | 本地 |
| POST | `/api/bt/ai/knowledge/rechunk` | 重新分块 | 本地 |
| POST | `/api/bt/ai/knowledge/reembed` | 重新嵌入 | 本地 |
| GET | `/api/bt/ai/knowledge/chat` | SSE 知识库聊天 | LLM |
| POST | `/api/bt/ai/knowledge/analyze/task` | 任务+KB检索 | 本地 |
| POST | `/api/bt/ai/knowledge/analyze/task/report` | 单任务LLM报告 | LLM |
| POST | `/api/bt/ai/knowledge/analyze/dashboard` | 仪表盘分析 | LLM |
| POST | `/api/bt/ai/task-analysis/fetch-tasks` | 拉取任务数据 | 本地 |
| POST | `/api/bt/ai/task-analysis/search-kb` | KB检索 | 本地(+LLM) |
| POST | `/api/bt/ai/task-analysis/generate-report` | 生成分析报告 | LLM×2 |
| POST | `/api/bt/ai/tbcreate/workspace/init` | 初始化工作区 | 本地 |
| GET | `/api/bt/ai/tbcreate/draft/current` | 读取草稿 | 本地 |
| POST | `/api/bt/ai/tbcreate/draft/save` | 保存草稿 | 本地 |
| GET | `/api/bt/ai/tbcreate/draft/events` | SSE草稿监听 | 本地 |
| POST | `/api/bt/ai/ttyd/session` | 创建终端会话 | ttyd进程 |
| POST | `/api/bt/ai/create_teambition` | 创建TB任务 | 钉钉 ⑨ |

---

## 七、关键文件索引

```
ai/
├── __init__.py              # 注册所有子模块路由
├── config.json              # LLM API 配置
├── knowledge/
│   ├── routes.py            # HTTP 端点 (14个) + _sync_workspace()
│   ├── service.py           # DingTalk API 客户端
│   ├── auto_sync.py         # 同步 pipeline (daemon调用)
│   ├── retriever.py         # search_hybrid / search_vector / search_chunks
│   ├── chunker.py           # 文档分块
│   ├── embedder.py          # 本地 embedding 模型
│   ├── parser.py            # 钉钉文档 → markdown
│   ├── chat.py              # SSE 流式聊天
│   ├── chat_session.py      # 聊天会话管理
│   ├── analyze.py           # 单任务 LLM 分析
│   ├── dashboard_analysis.py # 仪表盘 LLM 分析
│   ├── models.py            # KbDocument / KbChunk ORM
├── task_analysis/
│   ├── routes.py            # 3 端点
│   ├── data.py              # TB 任务数据查询
│   ├── retrieval.py         # 知识库检索封装
│   └── analysis.py          # LLM 报告生成
├── tbcreate/
│   ├── routes.py            # 6 端点 + SSE
│   ├── context.py           # 用户任务上下文
│   └── workspace.py         # 工作区初始化
├── terminal/
│   ├── routes.py            # ttyd 会话管理
│   ├── session.py           # 进程/端口/环境变量管理
│   └── launcher.sh          # ttyd → claude CLI 启动脚本
├── teambition/
│   ├── routes.py            # 创建任务端点
│   └── service.py           # 钉钉 TB 任务创建 API
├── mcp/
│   ├── server.py            # FastMCP 服务（resources/prompts/tools）
│   └── __main__.py          # MCP 入口
├── docs/                    # 设计文档
└── skills/                  # LLM prompt 模板
    ├── 1_tb_analysis/SKILL.md
    ├── 1-1_keyword_extract/SKILL.md
    ├── 2_tb_create/SKILL.md
    └── 3_kb_qa/SKILL.md
```
