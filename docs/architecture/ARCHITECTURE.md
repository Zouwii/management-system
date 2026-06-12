# Management System 后端架构

> 更新日期: 2026-06-05

## 目录

```
backend/
├── app.py                          # Flask 入口（薄封装 → base/app.py）
│
├── base/                           # 基础设施层（v2 重构：统一收敛）
│   ├── app.py                      #   create_app() + 3 个 daemon 后台线程
│   ├── api.py                      #   /api/bt 蓝图 + ok/fail 响应工具
│   ├── dingtalk_client.py          #   钉钉 OpenAPI 封装
│   ├── config.json                 #   应用配置
│   ├── ids.json                    #   用户/项目 ID 映射
│   │
│   ├── db/                         #   数据层
│   │   ├── config.py               #     DB 连接配置（读 .env）
│   │   ├── engine.py               #     SQLAlchemy engine + scoped_session
│   │   └── orm.py                  #     ORM 模型定义
│   │
│   ├── auth/                       #   登录认证
│   │   ├── routes.py               #     OAuth/免登/session/me/logout
│   │   └── service.py              #     角色推导、钉钉认证
│   ├── sync/                       #   数据同步
│   │   ├── routes.py               #     全量/增量/时间段
│   │   ├── task_sync.py            #     钉钉数据落库（A表/B表）
│   │   ├── lock.py                 #     分布式锁
│   │   └── task_detail_extract.py  #     任务详情提取
│   ├── projects/                   #   项目管理
│   │   ├── routes.py               #     任务搜索/列表/用户任务
│   │   └── task_service.py         #     钉钉 API 查询
│   ├── config/                     #   配置管理
│   │   ├── routes.py               #     配置读写
│   │   ├── service.py              #     配置服务 + 工时自动计算
│   │   └── member_visibility.py    #     成员可见性
│   ├── stats/                      #   统计汇总
│   ├── api_monitor.py              #   钉钉 API 调用监控（DB 持久化 + 按日查询）
│   │   └── routes.py               #
│   ├── health/                     #   健康检查/代理
│   │   ├── routes.py               #     health/gettoken/proxy
│   │   └── proxy.py                #     钉钉 API 代理
│   ├── route_registry/             #   路由注册
│   │   ├── __init__.py             #     register_all_routes() 统一挂载
│   │   ├── route_index.py          #     URL 映射索引
│   │   └── dashboard/              #     Dashboard 蓝图（workhour 路由入口）
│   ├── scripts/                    #   运维脚本
│   ├── static/                     #   前端静态资源（react 构建产物）
│   ├── runtime/                    #   运行时数据（日志等）
│   └── data/                       #   本地数据文件
│
├── ai/                             # AI 功能
│   ├── knowledge/                  #   知识库子系统
│   ├── task_analysis/              #   任务分析栏
│   ├── tbcreate/                   #   任务草稿创建
│   ├── teambition/                 #   TB 任务创建
│   ├── terminal/                   #   交互终端
│   ├── mcp/                        #   MCP Server（独立进程）
│   ├── skills/                     #   LLM prompt 模板
│   ├── domain/                     #   领域规则
│   └── docs/                       #   AI 设计文档
│
├── workhour/                       # 工时管理
│   ├── personal/                   #   个人工时
│   │   ├── routes.py               #     /api/dashboard/personal-hours
│   │   ├── aggregate.py            #     工时聚合查询
│   │   └── util.py                 #     工时解析工具
│   └── team/                       #   团队详情
│       └── routes.py               #     /api/dashboard/nav-team-detail
│
├── performance/                    # 绩效管理
│   ├── routes.py                   #   /api/bt/perf/*
│   └── service.py                  #   绩效计算
│
├── static/                         # 前端静态资源（Vue 回退）
└── runtime/                        # 运行时数据（AI 同步日志等）
```

## 分层架构

v2 重构后采用 **base 核心包 + 功能模块** 的扁平化结构。基础设施统一收敛到 `base/` 包内，功能模块（ai/、workhour/、performance/）按业务内聚各自维护路由与逻辑。

```
                        ┌──────────────┐
                        │   app.py     │  (薄封装，导入 base/app.py)
                        └──────┬───────┘
                               │
                    ┌──────────┴───────────┐
                    │    base/app.py       │  create_app() + 3 daemon threads
                    └──────────┬───────────┘
                               │
              ┌────────────────┼──────────────────┐
              │                │                   │
     ┌────────▼────────┐ ┌────▼─────┐   ┌─────────▼──────────┐
     │ base/api.py     │ │dashboard │   │ 功能模块 (ai/       │
     │ Blueprint       │ │Blueprint │   │  workhour/         │
     │ /api/bt         │ │/api/     │   │  performance/)     │
     └────────┬────────┘ │dashboard │   └────────────────────┘
              │          └────┬─────┘
     ┌────────▼────────┐     │
     │ route_registry/ │     │
     │ 统一注册:        │     │
     │  auth/sync/     │     │
     │  projects/config│     │
     │  stats/health/  │     │
     │  perf/ai        │     │
     └────────┬────────┘     │
              │              │
     ┌────────▼──────────────▼──────┐
     │  base/ 各子模块 (业务逻辑层)   │
     │  auth/ sync/ projects/       │
     │  config/ stats/ health/      │
     └────────┬─────────────────────┘
              │
     ┌────────▼────────┐
     │  base/db/       │  SQLAlchemy ORM + session
     │  base/          │  dingtalk_client.py
     └─────────────────┘
```

**依赖规则：**
- `base/db/` 和 `base/dingtalk_client.py` 为最底层，不依赖其他业务模块
- `base/` 子模块（auth/sync/projects/config/stats/health）依赖 `base/db/` 和 `base/dingtalk_client.py`
- `ai/`、`workhour/`、`performance/` 依赖 `base/db/` 和 `base/dingtalk_client.py`
- `route_registry/` 聚合所有模块的路由注册

### 例外：AI 模块

`ai/` 采用**功能模块化**模式，每个子功能（knowledge、task_analysis、tbcreate、terminal、teambition）将 routes 和 service 放在同一目录下，MCP Server 独立进程。AI 代码依赖紧密且不与其他业务共享。

### AI 知识库同步 → 检索 → 分析

```
POST /api/bt/ai/knowledge/sync-all        → 全量/增量同步（支持 full_sync 参数）
POST /api/bt/ai/knowledge/sync-and-embedding → 同步 + 分块 + 嵌入 pipeline
POST /api/bt/ai/knowledge/chunks/search   → 本地混合检索（FTS + vector RRF）
GET  /api/bt/ai/knowledge/chat            → SSE 流式知识库问答
POST /api/bt/ai/knowledge/analyze/dashboard → 6 模块仪表盘分析
```

**同步模式：**
- 小同步（每周一/四 04:00）：增量拉取新 ALIDOC 文档
- 大同步（每月 1 号 04:00）：对比 remote_modified_at 重拉变更文档
- pipeline: sync → rechunk → embed，日志写入 `runtime/logs/ai_sync_embed.log`

**检索架构：**
- MySQL FULLTEXT（keyword）+ pgvector cosine（semantic）→ RRF 融合排序
- embedding 模型：BAAI/bge-small-zh-v1.5（本地离线）

### AI 任务分析

```
POST /api/bt/ai/task-analysis/fetch-tasks      → 拉取季度任务数据
POST /api/bt/ai/task-analysis/search-kb         → 知识库检索
POST /api/bt/ai/task-analysis/generate-report   → LLM 生成 4 模块报告
```

### AI 任务创建 + 终端

```
POST /api/bt/ai/ttyd/session           → 创建 ttyd + Claude CLI 会话
POST /api/bt/ai/create_teambition      → 正式创建 TB 任务
MCP tools: get_user_task_context / save_task_draft / create_teambition_task
```

## 路由注册

`base/route_registry/__init__.py` 中的 `register_all_routes(bp, ok, fail)` 统一挂载所有模块：

```python
def register_all_routes(bp, ok, fail):
    register_health_proxy(bp, ok, fail)
    register_auth(bp, ok, fail)
    register_sync(bp, ok, fail)
    register_projects(bp, ok, fail)
    register_config(bp, ok, fail)
    register_ai_routes(bp, ok, fail)    # ai/ 包聚合了 5 个子模块
    register_perf(bp, ok, fail)
    register_stats(bp, ok, fail)
```

路由注册在 `base/api.py` 末尾调用：
```python
from base.route_registry import register_all_routes
register_all_routes(api_bp, _ok, _fail)
```

每个模块导出一个 `register(bp, ok, fail)` 函数，在函数内通过装饰器注册路由。

`base/app.py` 另外注册一个独立的 Dashboard 蓝图：
```python
from base.route_registry.dashboard import dashboard_bp
app.register_blueprint(dashboard_bp)
```

Dashboard 蓝图内部按需导入 workhour 路由模块：
```python
from workhour.personal import routes as _personal
from workhour.team import routes as _team
```

## 关键业务流程

### 用户登录

日常使用钉钉 OAuth 登录，钉钉 API 不可用时可通过离线模式登录。

**钉钉 OAuth 登录：**
```
GET  /api/bt/auth/dingtalk/url   → 获取钉钉 OAuth URL，前端跳转
GET  /api/bt/auth/callback       → 钉钉回调，交换 authCode → 用户信息
                                      → resolve_user_profile() 查 user_character 表
                                      → 确定角色/权限/homePath → 写入 session
POST /api/bt/auth/get_token      → 钉钉免登（移动端）
GET  /api/bt/auth/me             → 返回当前 session 中的用户信息
POST /api/bt/auth/logout         → 清除 session
```

**离线模式登录（钉钉 API 不可用时）：**
```
GET  /api/bt/auth/local/users    → 获取 user_character 表中可用用户列表
POST /api/bt/auth/local/login    → user_id + password → authenticate_local_user()
                                      → 查 user_character 表验证 → 建立 session
```

认证链路函数：`base/auth/routes.py` → `base/auth/service.py:authenticate_dingtalk_user()` 或 `authenticate_local_user()` → `resolve_user_profile()`

### 数据同步

```
POST /api/bt/full_update              → 全量更新（A表 + 线程池 B/C）
POST /api/bt/time_range_update        → 按时间范围更新 A+B（不更新 C）
POST /api/bt/db/sync/project-tasks    → 同步 A 表（项目任务列表）
POST /api/bt/db/sync/task-detail      → 同步单条 B 表记录
POST /api/bt/db/sync/task-details-batch → 批量同步 B 表记录
GET  /api/bt/update_lock_status       → 查询同步锁状态
```

所有同步入口在 `runtime/sync_disabled` 标记文件存在时返回 503（离线模式保护），检查点在 `base/sync/routes.py` 和 `base/projects/routes.py` 的 `_is_sync_disabled()` 函数。

full_update 流程：`base/sync/routes.py:full_update()` → 获取分布式锁 → `base/sync/task_sync.py:full_update_service()` → 释放锁

锁机制：`base/sync/lock.py` 操作 `update_locks` 表，TTL 防死锁。并发请求返回 409。

### AI 知识库同步 → 检索 → 分析

### Dashboard 工时

```
GET  /api/dashboard/personal-hours          → 工时页默认结构 + 成员选项
POST /api/dashboard/personal-hours/query    → 查询工时数据
POST /api/dashboard/personal-hours/update   → 触发工时更新
GET  /api/dashboard/nav-team-detail         → 导航组详情
GET  /api/dashboard/integration-team-detail → 对接组详情
```

## 角色与权限

| 角色 | 条件 | 数据范围 | 首页 |
|------|------|----------|------|
| employee | character ∈ {1,2,3} | self | /employee/personal-hours |
| manager | character = 0, 单一组长 | team | /manager/nav-team-detail 或 integration-team-detail |
| admin | character = 0, 同时是导航组长+对接组长 | all | /manager/department-overview |

权限推导链：`resolve_user_profile()` → `_derive_role_and_access()` → 返回 permissionCodes / homePath / dataScope

## API 响应规范

两个蓝图使用两套 `ok`/`fail` 辅助：

**`/api/bt/*`**（`base/api.py`）：
```python
ok(data)    → {"code": 200, "data": data, "error": ""}
fail(msg)   → {"code": 400, "data": {}, "error": msg}
```

**`/api/dashboard/*`**（`base/route_registry/dashboard/__init__.py`）：
```python
_ok(data)   → {"code": 200, "data": data, "error": ""}
_fail(msg)  → {"code": 400, "data": {}, "error": msg}
```

两个蓝图共享同一个 MySQL（通过 `base/db/` 的 SQLAlchemy session），但 dashboard 有自己的 session 鉴权（`_require_login()` 读 Flask session）。

## 数据库

- **主库 MySQL**：项目任务、工时、用户角色、配置、锁、知识库文档/分块 — `base/db/orm.py` 定义所有表
- **pgvector (PostgreSQL)**：语义向量存储（chunk_vectors）— 用于 knowledge-base RAG 检索
- **Perf 库 SQLite**：`performance/` 目录下的季度绩效考核数据
- ORM 使用 SQLAlchemy 2.x，`base/db/engine.py` 管理 scoped_session（适配 Flask 多线程）
- 表通过 `base/app.py` 启动时自动 create（`init_db(create_tables=True, drop_tables=False)`）

## 后台任务

`base/app.py` 的 `create_app()` 中启动 3 个 daemon 线程：

| 线程 | 触发条件 | 功能 |
|------|----------|------|
| `_auto_calc_loop` | 配置的时间点（如 02:00） | 根据 config 表自动触发工时更新 |
| `_auto_full_update_loop` | 每天北京时间 03:00 | 自动全量同步钉钉项目任务数据（A+B 表） |
| `_auto_knowledge_sync_loop` | 每周一/四 04:00（小同步）<br>每月 1 号 04:00（大同步） | 知识库文档同步 + 分块 + 嵌入 pipeline |

所有线程均用模块级标记避免重复启动，并自带锁机制防并发冲突。

## v2 重构变更摘要 (2026-06-05)

相比 v1，主要结构性变更：

| 变更项 | v1 路径 | v2 路径 |
|--------|---------|---------|
| 应用入口 | `app.py`（327 行） | `app.py`（7 行薄封装）+ `base/app.py`（324 行） |
| API 蓝图 | `api.py` | `base/api.py` |
| 钉钉客户端 | `dingtalk_client.py` | `base/dingtalk_client.py` |
| 数据层 | `db/` | `base/db/` |
| 服务层 | `services/`（已删除） | 拆分到 `base/auth/`、`base/sync/`、`base/projects/`、`base/config/`、`base/health/`、`base/stats/` |
| 路由注册 | `route_registry/` | `base/route_registry/` |
| 脚本/静态/运行时 | `scripts/`、`static/`、`runtime/`、`data/` | 移入 `base/` 对应目录 |
| workhour 路由 | `route_registry/dashboard/__init__.py` 直属 | `workhour/personal/`、`workhour/team/` 独立路由模块 |
| Docker 文件 | 存在（Dockerfile 等） | 已移除 |

**不变项：** `ai/`、`workhour/`、`performance/` 三个功能模块的目录结构保持不变。

## 开发约定

- 每个 Python 函数都有 Google-style docstring（Args / Returns / Raises）
- import 路径统一使用相对于 `backend/` 的 Python 路径（如 `from base.sync.lock import ...`）
- 钉钉 API 调用统一走 `base/dingtalk_client.py`（token 管理、请求封装、config.json/ids.json 读取）
- 基础设施代码放在 `base/` 包内（路由+服务分层），功能高度内聚的模块（如 AI）可在独立包内混合 routes+service
- 新增业务模块在 `base/route_registry/__init__.py` 中注册路由
