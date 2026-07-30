# 本体开发部数据平台

本项目是面向本体开发部的内部管理与 AI 辅助平台，覆盖工时统计、部门与团队看板、季度绩效、工作日耗时、Teambition 数据同步、知识库检索、AI 任务分析与任务创建等场景。

当前仓库采用 React 前端与 Flask 后端一体化部署：开发阶段由 Vite 提供前端服务并代理后端 API；生产构建会将前端产物输出到 Flask 静态目录，由同一后端进程提供页面和接口。

## 1 当前能力

| 模块 | 当前能力 |
| --- | --- |
| 登录与权限 | 钉钉 OAuth、钉钉内免登、本地离线登录、Flask Session、员工/主管/管理员角色与数据范围控制 |
| 工时管理 | 个人工时查询与更新、部门总览、导航组/对接组详情、成员与任务明细 |
| 工作日耗时 | 团队汇总、部门聚合、成员统计、任务状态与项目明细、考勤维护 |
| 季度绩效 | 个人绩效历史、档位与趋势、团队成员批量导入、单人编辑和重新计算 |
| 数据同步 | Teambition 项目任务增量同步、现场问题同步、需求池同步、同步锁与 API 调用监控 |
| AI 助理 | 任务与绩效分析、知识库浏览/同步/检索/问答、任务草稿、Teambition 任务创建、交互终端 |
| 知识沉淀 | RAG 检索优化材料、AI 领域规则、业务流程以及数据库和运维设计文档 |

## 2 技术栈

### 2.1 前端

- React 19
- React Router 7
- Vite 8
- Tailwind CSS 3
- Zustand 5
- Recharts 3
- DingTalk JSAPI

### 2.2 后端

- Python 3.10+
- Flask 2.3
- SQLAlchemy 2
- APScheduler
- Poetry
- MySQL / SQLite
- PostgreSQL + pgvector
- Sentence Transformers / FlagEmbedding

## 3 仓库结构

```text
.
├── frontend-react/              # React 前端
│   ├── src/
│   │   ├── api/                 # mock/real 请求层
│   │   ├── components/          # 通用组件
│   │   ├── constants/           # 路由、角色、权限和 API 常量
│   │   ├── layouts/             # 员工端与管理端布局
│   │   ├── pages/               # 业务页面
│   │   ├── router/              # 路由配置与守卫
│   │   ├── store/               # Zustand 状态
│   │   └── utils/               # 工时、权限等工具
│   └── vite.config.js           # 开发代理与生产输出配置
├── backend/
│   ├── app.py                   # 后端启动入口
│   ├── base/                    # 应用工厂、认证、数据库、同步和基础业务
│   ├── workhour/                # 个人/团队工时与工作日耗时
│   ├── performance/             # 季度绩效
│   ├── ai/                      # 知识库、任务分析、任务创建、MCP 和终端
│   ├── static/react/            # 前端生产构建产物
│   ├── scripts/                 # 数据迁移与维护脚本
│   ├── pyproject.toml           # Python 依赖
│   └── .env.example             # 后端环境变量示例
├── docs/                        # 架构、业务、数据库、AI 和运维文档
├── scripts/                     # 打包、部署与 MCP 配置脚本
├── pgvector-compose.yml         # pgvector 本地服务
└── onekey-deploy.sh             # 打包并部署
```

后端采用 `base` 核心包加业务模块的结构。`backend/base/route_registry/` 统一注册 `/api/bt/*` 路由，工时看板使用独立的 `/api/dashboard/*` Blueprint。完整调用关系见[架构说明](docs/architecture/ARCHITECTURE.md)。

## 4 页面与路由

路由配置位于 [`frontend-react/src/router/routeConfig.jsx`](frontend-react/src/router/routeConfig.jsx)。

| 页面 | 路径 | 可访问角色 |
| --- | --- | --- |
| 登录 | `/login` | 公开 |
| 部门有效工时 | `/manager/department-overview` | 主管、管理员 |
| 导航组详情 | `/manager/nav-team-detail` | 主管、管理员 |
| 对接组详情 | `/manager/integration-team-detail` | 主管、管理员 |
| 工作日耗时 | `/manager/workday-costhour` | 主管、管理员 |
| 个人工时 | `/employee/personal-hours` | 员工、主管、管理员 |
| 绩效管理 | `/employee/performance` | 员工、主管、管理员 |
| AI 助理 | `/employee/ai-analysis` | 员工、主管、管理员 |
| 完整展开版 | `/prototype` | 管理员 |

用户登录后会根据角色、所属团队和权限码进入对应首页。权限控制包括路由权限、按钮权限和数据范围权限，核心定义位于：

- [`frontend-react/src/constants/permissionCodes.js`](frontend-react/src/constants/permissionCodes.js)
- [`frontend-react/src/constants/permissions.js`](frontend-react/src/constants/permissions.js)
- [`frontend-react/src/router/guards.jsx`](frontend-react/src/router/guards.jsx)

## 5 本地开发

### 5.1 前置条件

- Python 3.10+
- Poetry；未使用 Poetry 时也可按 `backend/requirements.txt` 安装依赖
- Node.js 与 npm，版本需满足 Vite 8 的运行要求
- 可选：MySQL，用于接近生产环境的数据存储
- 可选：Docker Compose，用于启动 pgvector 语义向量库

### 5.2 选择运行方式

本地开发支持以下两种方式：

| 方式 | 启动内容 | 适用场景 | 前端热更新 |
| --- | --- | --- | --- |
| mock 模式 | 仅启动 Vite 前端，使用前端模拟数据 | 页面布局、样式、组件、路由和普通交互开发 | 支持 |
| real 联调模式 | 启动 Flask、MCP SSE 和 Vite，连接真实接口 | 数据库、钉钉登录、数据同步、绩效导入和 AI 功能验证 | 支持 |

### 5.3 方式一：前端 mock 模式

仓库中的 `frontend-react/.env` 默认设置为 `VITE_API_MODE=mock`。

```bash
cd frontend-react
npm ci
npm run mock
```

启动后访问 `http://localhost:5173/login`。修改 `frontend-react/src/` 下的代码并保存后，Vite 会自动更新页面，不需要手动重启。

mock 模式不启动 Flask、MySQL、pgvector 或 MCP，因此不适合验证真实登录、后端接口、数据同步和 AI 知识库功能。登录时可使用以下演示账号：

| 账号 | 密码 | 角色 |
| --- | --- | --- |
| `employee` | `123456` | 员工 |
| `navManager` | `123456` | 导航组主管 |
| `servoManager` | `123456` | 对接组主管 |
| `admin` | `123456` | 管理员 |

### 5.4 方式二：真实后端一键联调

需要使用真实后端接口开发时，可在项目根目录运行：

```bash
./debug-deploy.sh
```

该脚本会释放本机 `5001`、`5200` 端口，并依次启动：

- Flask 后端：`http://localhost:5001`
- MCP SSE：`http://localhost:5200/sse`
- Vite 前端：`http://localhost:5173`

修改 `frontend-react/src/` 下的代码并保存后，Vite 会通过 HMR 自动更新页面。当前 Flask 启动入口未开启代码自动重载；修改后端 Python 代码后，需要按 `Ctrl+C` 停止脚本并重新运行。

无论本地使用 mock 还是 real 模式，正式部署时 `scripts/02-package.sh` 都会默认以 `VITE_API_MODE=real` 重新构建前端，不会把 mock 模式部署到服务器。

### 5.5 手动启动真实前后端

首次运行时复制后端配置，然后启动 Flask：

```bash
test -f backend/.env || cp backend/.env.example backend/.env
cd backend
poetry install --no-root
poetry run python app.py
```

后端本地默认监听 `http://localhost:5001`。在另一个终端启动真实接口模式：

```bash
cd frontend-react
npm ci
npm run dev:real
```

Vite 会把 `/api` 请求代理到 `http://localhost:5001`，前端访问地址仍为 `http://localhost:5173`。

未配置 MySQL 时，后端业务数据库默认使用 `backend/data/` 下的 SQLite 文件。钉钉登录和实际业务数据同步仍需要有效的钉钉应用配置。

### 5.6 启用知识库向量检索

知识库的关键词检索可使用业务数据库；语义向量检索需要 PostgreSQL + pgvector：

```bash
docker compose -f pgvector-compose.yml up -d
```

对应连接参数为 `PGVECTOR_HOST`、`PGVECTOR_PORT`、`PGVECTOR_USER`、`PGVECTOR_PASSWORD`、`PGVECTOR_DB`，也可直接配置 `PGVECTOR_DATABASE_URI`。

## 6 环境配置

### 6.1 前端变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `VITE_API_MODE` | 代码默认 `real`；仓库 `.env` 为 `mock` | `mock` 使用本地模拟数据，`real` 请求 Flask API |
| `VITE_API_BASE_URL` | `/api` | API 基础路径 |

### 6.2 后端变量

后端优先读取 `TB_TOOL_BT_*`，并兼容旧的 `TB_TOOL_B1_*` 变量名。完整示例见 [`backend/.env.example`](backend/.env.example)。

| 配置组 | 主要变量 |
| --- | --- |
| 钉钉登录 | `DINGTALK_APPKEY`、`DINGTALK_APPSECRET`、`DINGTALK_CORP_ID`、`DINGTALK_REDIRECT_URI` |
| Session/CORS | `SECRET_KEY`、`SESSION_COOKIE_SAMESITE`、`SESSION_COOKIE_SECURE`、`SESSION_EXPIRE_SECONDS`、`CORS_ORIGINS` |
| 主数据库 | `TB_TOOL_BT_USE_MYSQL`、`TB_TOOL_BT_DATABASE_URI` 或 `TB_TOOL_BT_DB_HOST/PORT/USER/PASSWORD/NAME` |
| 业务分库 | `TB_TOOL_BT_KB_DATABASE_URI`、`TB_TOOL_BT_PERF_DATABASE_URI`、`TB_TOOL_BT_ONSITE_DATABASE_URI`、`TB_TOOL_BT_REQ_POOL_DATABASE_URI` |
| 向量库 | `PGVECTOR_DATABASE_URI` 或 `PGVECTOR_HOST/PORT/USER/PASSWORD/DB` |
| AI 运行 | `AI_PRELOAD_EMBEDDING`、`AI_FLASK_BASE_URL`、`AI_TTYD_BASE_URL` |

不要提交真实密钥、数据库密码或生产 `.env`。

## 7 API 概览

后端提供两组主要接口：

- `/api/bt/*`：认证、配置、同步、绩效、统计、AI、现场问题和需求池。
- `/api/dashboard/*`：个人工时、团队工时和绩效历史等看板接口。

服务启动后可通过 `GET /api/bt/routes` 查看后端维护的路由索引，通过 `GET /api/bt/health` 探活，通过 `GET /api/bt/monitor/api-stats` 查看钉钉 API 调用统计。

常用接口包括：

| 领域 | 接口示例 |
| --- | --- |
| 认证 | `/api/bt/auth/dingtalk/url`、`/api/bt/auth/local/login`、`/api/bt/auth/me` |
| 工时 | `/api/dashboard/personal-hours`、`/api/dashboard/nav-team-detail` |
| 部门 | `/api/bt/dashboard/department-overview` |
| 绩效 | `/api/bt/perf/query`、`/api/bt/perf/batch-import`、`/api/bt/perf/update-quarter-member` |
| 工作日耗时 | `/api/bt/stats/workday_costhour/team_summary`、`/api/bt/stats/attendance/save` |
| AI 知识库 | `/api/bt/ai/knowledge/sync-all`、`/api/bt/ai/knowledge/chunks/search`、`/api/bt/ai/knowledge/chat` |
| AI 任务 | `/api/bt/ai/task-analysis/generate-report`、`/api/bt/ai/tbcreate/draft/save`、`/api/bt/ai/create_teambition` |
| 数据同步 | `/api/bt/increase_sync`、`/api/bt/onsite/sync`、`/api/bt/req-pool/sync` |

## 8 构建与部署

### 8.1 构建前端并由 Flask 托管

```bash
cd frontend-react
npm ci
VITE_API_MODE=real npm run build
cd ../backend
poetry run python app.py
```

Vite 构建结果会写入 `backend/static/react/`。Flask 对非 API 路径提供 SPA fallback，因此生产环境直接访问 `/login` 等前端路由不会返回 404。

### 8.2 守护进程

服务器脚本默认使用端口 `5002`，支持 `start`、`stop`、`restart`、`status` 和 `logs`：

```bash
cd backend
bash run_on_pc_daemon.sh start
bash run_on_pc_daemon.sh status
```

### 8.3 打包脚本

```bash
./scripts/02-package.sh
```

脚本会以 `real` 模式构建前端，并将部署所需后端文件打包到 `tar/`。`./onekey-deploy.sh` 会继续执行仓库内配置的远程部署流程，仅应在确认目标环境和权限后使用。

## 9 常用脚本

仓库清理后，仅保留当前开发和发布流程仍在使用的脚本：

| 脚本 | 功能 | 关键行为与注意事项 |
| --- | --- | --- |
| [`debug-deploy.sh`](debug-deploy.sh) | 一键启动本地联调环境 | 释放 `5001`、`5200` 端口，启动 Flask、MCP SSE 和 Vite real 模式；前端支持热更新，按 `Ctrl+C` 后清理后端和 MCP 进程 |
| [`backend/run_on_pc_daemon.sh`](backend/run_on_pc_daemon.sh) | 管理后端守护进程 | 支持 `start/stop/restart/status/logs`；启动时检查运行环境、安装依赖并按需创建 `.env`，可通过 `INIT_MYSQL=1` 初始化 MySQL；默认端口为 `5002` |
| [`scripts/02-package.sh`](scripts/02-package.sh) | 构建并生成部署包 | 默认以 `real` 模式构建前端；复制后端和共享 AI skills，排除 `.venv`、业务数据、运行日志、本地模型与缓存，生成 `tar/tb_tool_bt_backend-<时间>.tar.gz` |
| [`scripts/03-deploy.sh`](scripts/03-deploy.sh) | 部署最新压缩包 | 选择 `tar/` 中最新包上传到脚本内指定服务器；替换远程项目时保留并恢复 `.venv`、`.env`、`data` 和 `local_models`，然后重启守护进程；上传后会删除本地压缩包 |
| [`onekey-deploy.sh`](onekey-deploy.sh) | 一键打包并部署 | 依次执行 `scripts/02-package.sh` 和 `scripts/03-deploy.sh` |
| [`scripts/setup-mcp.sh`](scripts/setup-mcp.sh) | 配置 Claude Code 使用 TB MCP | 交互式读取用户名，备份并重写 `~/.claude/mcp.json`，同时启用 `tb-mcp`；会修改当前用户的 Claude 全局配置 |

打包但不部署：

```bash
./scripts/02-package.sh
```

打包并部署：

```bash
./onekey-deploy.sh
```

部署脚本包含固定的远程目标配置，并会替换服务器上的现有项目目录。执行 `scripts/03-deploy.sh` 或 `onekey-deploy.sh` 前，必须核对目标服务器、待上传包以及远端保留目录。

现场问题、需求池和知识库的一次性循环同步工具，以及旧 DiagKit 运维脚本已从本仓库移除；相关业务能力仍通过 Flask API 提供。

## 10 质量检查

前端当前提供构建与 ESLint 检查：

```bash
cd frontend-react
npm run lint
npm run build
```

仓库暂未定义统一的前后端自动化测试命令。提交涉及后端接口或数据迁移的改动时，应结合对应模块文档与实际环境补充验证。

## 11 文档导航

- [文档总索引](docs/README.md)
- [后端架构](docs/architecture/ARCHITECTURE.md)
- [同步与锁设计](docs/architecture/sync-and-lock.md)
- [数据库设计](docs/database/database-design.md)
- [季度绩效计算说明](docs/business/季度绩效计算说明.md)
- [工作日耗时设计](docs/business/workday-costhour-design.md)
- [AI 架构](docs/ai/design/architecture/11-ai-architecture.md)
- [MCP 使用说明](docs/ai/MCP_使用说明.md)
- [服务器运维说明](docs/ops/server-connection.md)
