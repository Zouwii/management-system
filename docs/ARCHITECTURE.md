# Management System 后端架构

## 目录

```
backend/
├── app.py                          # Flask 入口，create_app()
├── api.py                          # /api/bt 蓝图 + ok/fail 工具函数
├── dingtalk_client.py              # 钉钉 OpenAPI 封装
├── config.json                     # 应用配置
├── ids.json                        # 用户/项目 ID 映射
│
├── db/                             # 数据层
│   ├── config.py                   # DB 连接配置（读 .env）
│   ├── engine.py                   # SQLAlchemy engine + session
│   └── orm.py                      # ORM 模型定义
│
├── base/                           # 基础建设
│   ├── auth/                       #   登录认证
│   │   ├── routes.py               #     OAuth/免登/session
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
│   │   ├── service.py              #     配置服务
│   │   └── member_visibility.py    #     成员可见性
│   ├── stats/                      #   统计汇总
│   │   └── routes.py               #
│   └── health/                     #   健康检查/代理
│       ├── routes.py               #     health/gettoken/proxy
│       └── proxy.py                #     钉钉 API 代理
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
├── ai/                             # AI 功能
│   ├── knowledge/                  #   知识库子系统
│   ├── task_analysis/              #   任务分析栏
│   ├── tbcreate/                   #   任务草稿创建
│   ├── teambition/                 #   TB 任务创建
│   ├── terminal/                   #   交互终端
│   ├── mcp/                        #   MCP Server
│   ├── skills/                     #   LLM prompt 模板
│   ├── domain/                     #   领域规则
│   └── docs/                       #   AI 设计文档
│
├── route_registry/                 # 兼容层 — 路由入口索引
│   ├── __init__.py                 #   → 实际指向 base/、performance/
│   ├── route_index.py              #   URL 映射索引
│   └── dashboard/                  #   Dashboard 蓝图（workhour 路由）
│
├── services/                       # 废弃 — 旧服务代码（已迁移）
├── data/                           # 本地数据文件
├── static/                         # 前端静态资源
├── runtime/                        # 运行时数据
└── scripts/                        # 运维脚本
```

## 分层架构

采用三层架构，严格遵循 **路由层 → 服务层 → 数据层** 的单向依赖。

```
route_registry/  (HTTP 请求/响应、session、参数校验)
       │
       ▼
services/        (业务逻辑、钉钉 API 调用、数据落库)
       │
       ▼
db/              (SQLAlchemy ORM、连接管理)
```

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

`route_registry/__init__.py` 中的 `register_all_routes(bp, ok, fail)` 统一挂载所有模块：

```python
def register_all_routes(bp, ok, fail):
    register_health_proxy(bp, ok, fail)
    register_auth(bp, ok, fail)
    register_sync(bp, ok, fail)
    register_projects(bp, ok, fail)
    register_config(bp, ok, fail)
    register_ai_routes(bp, ok, fail)    # ai/ 包聚合了 3 个子模块
    register_perf(bp, ok, fail)
    register_stats(bp, ok, fail)
```

每个模块导出一个 `register(bp, ok, fail)` 函数，在函数内通过装饰器注册路由。

`app.py` 另外注册一个独立的 Dashboard 蓝图：
```python
from route_registry.dashboard import dashboard_bp
app.register_blueprint(dashboard_bp)
```

## 关键业务流程

### 用户登录

```
GET  /api/bt/auth/dingtalk/url   → 获取钉钉 OAuth URL，前端跳转
GET  /api/bt/auth/callback       → 钉钉回调，交换 authCode → 用户信息
                                      → resolve_user_profile() 查 user_character 表
                                      → 确定角色/权限/homePath → 写入 session
POST /api/bt/auth/get_token      → 钉钉免登（移动端）
GET  /api/bt/auth/me             → 返回当前 session 中的用户信息
POST /api/bt/auth/logout         → 清除 session
```

认证链路函数：`route_registry/auth.py:_session_from_dingtalk_auth_code()` → `services/auth_service.py:authenticate_dingtalk_user()` → `resolve_user_profile()`

### 数据同步

```
POST /api/bt/full_update              → 全量更新（A表 + 线程池 B/C）
POST /api/bt/time_range_update        → 按时间范围更新 A+B（不更新 C）
POST /api/bt/db/sync/project-tasks    → 同步 A 表（项目任务列表）
POST /api/bt/db/sync/task-detail      → 同步单条 B 表记录
POST /api/bt/db/sync/task-details-batch → 批量同步 B 表记录
GET  /api/bt/update_lock_status       → 查询同步锁状态
```

full_update 流程：`route_registry/sync.py:full_update()` → 获取分布式锁 → `services/task_sync_service.py:full_update_service()` → 释放锁

锁机制：`services/sync_lock.py` 操作 `update_locks` 表，TTL 防死锁。并发请求返回 409。

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

**`/api/bt/*`**（`api.py`）：
```python
ok(data)    → {"code": 200, "data": data, "error": ""}
fail(msg)   → {"code": 400, "data": {}, "error": msg}
```

**`/api/dashboard/*`**（`route_registry/dashboard/__init__.py`）：
```python
_ok(data)   → {"code": 200, "data": data, "error": ""}
_fail(msg)  → {"code": 400, "data": {}, "error": msg}
```

两个蓝图共享同一个 MySQL（通过 `db/` 的 SQLAlchemy session），但 dashboard 有自己的 session 鉴权（`_require_login()` 读 Flask session）。

## 数据库

- **主库 MySQL**：项目任务、工时、用户角色、配置、锁、知识库文档/分块 — `db/orm.py` 定义所有表
- **pgvector (PostgreSQL)**：语义向量存储（chunk_vectors）— 用于 knowledge-base RAG 检索
- **Perf 库 SQLite**：`perf/` 目录下的季度绩效考核数据
- ORM 使用 SQLAlchemy 2.x，`db/engine.py` 管理 scoped_session（适配 Flask 多线程）
- 表通过 `app.py` 启动时自动 create（`init_db(create_tables=True, drop_tables=False)`）

## 开发约定

- 每个 Python 函数都有 Google-style docstring（Args / Returns / Raises）
- import 路径统一使用相对于 `backend/` 的 Python 路径（如 `from services.sync_lock import ...`）
- 钉钉 API 调用统一走 `dingtalk_client.py`（token 管理、请求封装、config.json/ids.json 读取）
- 新业务功能优先在 `route_registry/` 和 `services/` 分层，如果功能高度内聚（如 AI），可在独立包内混合 routes+service
