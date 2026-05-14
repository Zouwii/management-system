# Management System 后端架构

## 目录

```
backend/
├── app.py                          # Flask 入口，create_app()
├── api.py                          # /api/bt 蓝图 + ok/fail 工具函数
│
├── db/                             # 数据层
│   ├── config.py                   # DB 连接配置（读 .env）
│   ├── engine.py                   # SQLAlchemy engine + session
│   └── orm.py                      # ORM 模型定义
│
├── route_registry/                 # 路由层 — 每个业务一个模块
│   ├── __init__.py                 # register_all_routes(bp, ok, fail)
│   ├── route_index.py              # URL → handler → service 映射索引
│   ├── auth.py                     # 钉钉登录（OAuth/免登/session）
│   ├── sync.py                     # 数据同步（全量/时间段/A表/B表/批量）+ 锁状态
│   ├── projects.py                 # 项目任务搜索/列表/用户任务/自定义字段
│   ├── config_routes.py            # 配置读写（userid/时间范围/工时系数）
│   ├── perf.py                     # 绩效 fill / calculate
│   ├── stats.py                    # 统计汇总
│   ├── health_proxy.py             # 健康检查 / 钉钉代理 / gettoken
│   └── dashboard/                  # Dashboard 蓝图 (/api/dashboard)
│       ├── __init__.py             # dashboard_bp 创建 + 共享工具函数
│       ├── personal_hours.py       # 个人工时页（默认结构/查询/更新）
│       ├── team_detail.py          # 导航组/对接组详情
│       └── ai_task.py              # AI 创建任务单
│
├── services/                       # 业务逻辑层 — 被路由层调用
│   ├── auth_service.py             # 角色推导、用户画像解析、钉钉认证
│   ├── task_sync_service.py        # 钉钉数据落库（A表/B表/全量/增量）
│   ├── project_task_service.py     # 钉钉 API 查询（项目任务/用户任务）
│   ├── sync_lock.py                # 分布式锁（UpdateLock 表操作）
│   ├── proxy_service.py            # 钉钉 API 代理
│   ├── config_service.py           # 配置管理
│   ├── perf_service.py             # 绩效计算
│   ├── workhour_aggregate_service.py  # 工时聚合
│   ├── workhour_util.py            # 工时解析工具
│   ├── task_detail_extract_service.py # 任务详情自定义字段提取
│   └── member_visibility.py        # 成员可见性
│
├── ai/                             # AI 功能 — 按子功能分包（routes+service 同目录）
│   ├── __init__.py                 # register_all_routes(bp, ok, fail)
│   ├── config.json                 # one-api 网关配置
│   ├── task_assistant/             # AI 任务助手：对话→草稿
│   │   ├── routes.py               #   HTTP 路由
│   │   ├── service.py              #   对话管理 + 草稿合并
│   │   └── context.py              #   DB 任务上下文读取
│   ├── mission/                    # AI 任务创建：草稿→钉钉
│   │   ├── routes.py               #   HTTP 路由
│   │   └── service.py              #   构建 Payload → 创建 TB 任务
│   ├── terminal/                   # AI 终端：ttyd + Claude CLI
│   │   ├── routes.py               #   HTTP 路由（models/session）
│   │   ├── session.py              #   ttyd session 生命周期管理
│   │   └── launcher.sh             #   模型选择菜单 + Claude CLI 启动
│   ├── scripts/                    # Claude Code CLI 安装/启动辅助脚本
│   ├── rules/                      # AI 行为规则（供 LLM prompt 使用）
│   └── docs/                       # AI 设计文档
│
├── dingtalk_client.py              # 钉钉 OpenAPI 封装（token/用户/项目/auth）
├── config.json                     # 应用配置（corpId/clientId 等）
├── ids.json                        # 用户/项目 ID 映射
│
├── data/                           # 本地数据文件
├── static/                         # 前端静态资源（react/vue 构建产物）
├── runtime/                        # 运行时数据（Claude 工作区、用户会话）
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

`ai/` 采用**功能模块化**模式，每个子功能（task_assistant、mission、terminal）将 routes 和 service 放在同一目录下。因为 AI 相关代码依赖紧密且不与其他业务共享，这种组织方式比分层更可读。

```
ai/
├── task_assistant/
│   ├── routes.py    # 仅这一层的路由
│   ├── service.py   # 仅这一层的业务逻辑
│   └── context.py   # 仅这一层的上下文读取
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

### AI 任务助手

```
POST /api/bt/ai/task_assistant/conversations      → 创建对话
GET  /api/bt/ai/task_assistant/conversations/<id>  → 获取对话（含任务上下文）
POST /api/bt/ai/task_assistant/conversations/<id>/messages → 发送消息
POST /api/bt/ai/task_assistant/draft               → 确认草稿（合并 LLM 输出）
```

### AI 任务创建

```
POST /api/bt/ai/create_mission/payload  → 调试：预览创建参数
POST /api/bt/ai/create_mission          → 根据草稿构建参数，调钉钉 API 创建任务
POST /api/dashboard/ai-task-ticket       → 前端确认草稿后创建 TB 任务
```

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

- **主库 MySQL**：项目任务、工时、用户角色、配置、锁 — `db/orm.py` 定义所有表
- **Perf 库 SQLite**：`perf/` 目录下的季度绩效考核数据
- ORM 使用 SQLAlchemy 2.x，`db/engine.py` 管理 scoped_session（适配 Flask 多线程）
- 表通过 `app.py` 启动时自动 create（`init_db(create_tables=True, drop_tables=False)`）

## 开发约定

- 每个 Python 函数都有 Google-style docstring（Args / Returns / Raises）
- import 路径统一使用相对于 `backend/` 的 Python 路径（如 `from services.sync_lock import ...`）
- 钉钉 API 调用统一走 `dingtalk_client.py`（token 管理、请求封装、config.json/ids.json 读取）
- 新业务功能优先在 `route_registry/` 和 `services/` 分层，如果功能高度内聚（如 AI），可在独立包内混合 routes+service
