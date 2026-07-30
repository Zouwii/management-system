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
| 知识沉淀 | RAG 检索优化材料、错误码知识库、现场问题分析、业务与数据库设计文档 |

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
├── scripts/                     # 打包、部署、同步与运维脚本
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

### 5.2 仅运行前端 mock

仓库中的 `frontend-react/.env` 默认设置为 `VITE_API_MODE=mock`。

```bash
cd frontend-react
npm ci
npm run mock
```

访问 `http://localhost:5173/login`，可使用以下演示账号：

| 账号 | 密码 | 角色 |
| --- | --- | --- |
| `employee` | `123456` | 员工 |
| `navManager` | `123456` | 导航组主管 |
| `servoManager` | `123456` | 对接组主管 |
| `admin` | `123456` | 管理员 |

### 5.3 前后端联调

复制后端配置并启动 Flask：

```bash
cp backend/.env.example backend/.env
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

### 5.4 启用知识库向量检索

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

### 9.1 开发、打包与部署

| 脚本 | 功能 | 关键行为与注意事项 |
| --- | --- | --- |
| [`debug-deploy.sh`](debug-deploy.sh) | 一键启动本地联调环境 | 释放 `5001`、`5200` 端口，依次启动 Flask、MCP SSE 和 Vite real 模式；按 `Ctrl+C` 后清理后端和 MCP 进程。依赖 Poetry、npm、curl 和 fuser |
| [`backend/run_on_pc_daemon.sh`](backend/run_on_pc_daemon.sh) | 管理后端守护进程 | 支持 `start/stop/restart/status/logs`；启动时检查运行环境、安装依赖、按需创建 `.env`，可通过 `INIT_MYSQL=1` 初始化 MySQL；默认服务端口为 `5002` |
| [`scripts/01-install-hooks.sh`](scripts/01-install-hooks.sh) | 安装仓库 `pre-push` Hook | 设计用途是把 `.githooks/pre-push` 安装到 `.git/hooks/`。当前脚本以 `scripts/` 作为路径基准，无法找到仓库根目录下的 Hook，修正路径前不建议直接使用 |
| [`scripts/02-package.sh`](scripts/02-package.sh) | 构建并生成部署包 | 默认以 `VITE_API_MODE=real` 构建前端，将产物写入后端静态目录；复制后端和共享 AI skills，排除 `.venv`、数据、运行日志、本地模型与缓存，输出时间戳命名的 `tar/tb_tool_bt_backend-*.tar.gz` |
| [`scripts/03-deploy.sh`](scripts/03-deploy.sh) | 部署最新压缩包 | 找到 `tar/` 中最新包并上传到脚本内指定服务器；远端替换项目目录前暂存并恢复 `.venv`、`.env`、`data` 和 `local_models`，随后重启守护进程；部署成功前流程中会删除本地压缩包 |
| [`scripts/04-tag-package.sh`](scripts/04-tag-package.sh) | 创建版本 Tag 并打包 | 用法为 `./scripts/04-tag-package.sh <tag> [message] [--push]`；创建本地 Tag 后调用 `02-package.sh`，指定 `--push` 时再推送 Tag |
| [`onekey-deploy.sh`](onekey-deploy.sh) | 串联打包和部署 | 顺序执行 `02-package.sh` 与 `03-deploy.sh`。该流程会更新远程项目并重启服务，只适用于已确认目标服务器的正式部署 |

常用本地联调命令：

```bash
./debug-deploy.sh
```

常用发布命令：

```bash
./scripts/02-package.sh
./scripts/04-tag-package.sh v1.4.0 "release v1.4.0"
```

部署脚本内包含固定的远程目标配置，并会替换服务器上的现有项目目录。执行 `scripts/03-deploy.sh` 或 `onekey-deploy.sh` 前，必须先核对脚本中的目标环境、待上传包和远端备份策略。

### 9.2 数据同步与知识库脚本

| 脚本 | 功能 | 运行前提或副作用 |
| --- | --- | --- |
| [`sync-onsite-a-loop.sh`](sync-onsite-a-loop.sh) | 从当前游标循环续拉现场问题 A 表 | 调用本机 `5002` 服务，不重置游标，不触发 B 表；参数为钉钉 `userId` |
| [`sync-onsite-loop.sh`](sync-onsite-loop.sh) | 重新执行现场问题完整同步 | 调用脚本内指定的远程服务，先重置现场问题游标，再循环调用 `/onsite/sync` 同步 A、B 表；会改变同步游标 |
| [`sync-reqpool-a-loop.sh`](sync-reqpool-a-loop.sh) | 从当前游标循环续拉需求池 A 表 | 调用本机 `5002` 服务，不重置游标，不触发 B 表；参数为钉钉 `userId` |
| [`sync-reqpool-loop.sh`](sync-reqpool-loop.sh) | 重置后重新拉取需求池 A 表 | 调用脚本内指定的远程服务，先重置需求池游标，再循环调用 `/req-pool/sync-a`；当前实现只同步 A 表 |
| [`scripts/kb_raw_sync.py`](scripts/kb_raw_sync.py) | 绕过 Flask 直接拉取钉钉知识库 | 不写 `api_call_logs`，默认筛选 priority 99 的知识库并写入本地 SQLite；支持 `--estimate-only`、`--ws`、`--uid`、`--db` 和 `--dump-sql` |
| [`scripts/selective_sync.py`](scripts/selective_sync.py) | 定向同步指定知识库文件夹 | 支持递归、只预览、下载正文，并可写入 `errcode_documents` 或 `kb_documents`；当前实现包含服务器代码路径和 MySQL 连接假设，适合目标服务器环境 |
| [`scripts/errcode_asset_extractor.py`](scripts/errcode_asset_extractor.py) | 提取错误码文档中的图片、附件和表格引用 | 支持单个 `doc_id` 或 `--all`，结果写入 `errcode_assets`；依赖知识库用户身份和目标 MySQL 表 |
| [`scripts/kb_sync_measure.sh`](scripts/kb_sync_measure.sh) | 测量多个知识库同步的钉钉 API 用量 | 逐库调用同步 API并生成运行日志和汇总；开始时会清空主库 `api_call_logs`，仅可在明确允许重置统计数据的测试环境执行 |

断点续拉示例：

```bash
./sync-onsite-a-loop.sh <userId>
./sync-reqpool-a-loop.sh <userId>
```

知识库同步预估示例：

```bash
cd scripts
python3 kb_raw_sync.py --estimate-only
python3 selective_sync.py <workspace_id> <folder_node_id> --recursive --dry-run
```

### 9.3 MCP 与历史 DiagKit 脚本

| 脚本 | 功能 | 当前状态 |
| --- | --- | --- |
| [`setup-mcp.sh`](setup-mcp.sh) | 配置 Claude Code 连接 TB MCP SSE 服务 | 交互式读取用户名，备份并重写 `~/.claude/mcp.json`，同时更新 `~/.claude/settings.local.json`；会修改当前用户的全局 Claude 配置 |
| [`scripts/deploy-diagkit-scripts.sh`](scripts/deploy-diagkit-scripts.sh) | 上传 DiagKit 服务、登录代理和清理脚本 | 面向脚本内指定服务器，并会在远端安装系统依赖 |
| [`scripts/manage-diagkit-ttyd.sh`](scripts/manage-diagkit-ttyd.sh) | 远程管理 DiagKit ttyd 服务 | 通过 SSH 调用远端服务脚本，支持 `start/stop/restart/status` |
| [`scripts/diagkit-ttyd-service.sh`](scripts/diagkit-ttyd-service.sh) | 管理 auth-proxy 与 ttyd 进程 | 对外 auth-proxy 和内部 ttyd 双进程结构，同时注册过期诊断材料清理任务 |
| [`scripts/diagkit-cleanup.sh`](scripts/diagkit-cleanup.sh) | 清理过期诊断原始材料 | 默认删除 7 天前 Case 中的 `raw/`、`extracted/` 和 `tmp/`，保留报告等文本产物；支持 `--dry-run` |

DiagKit 已在 `onekey-deploy.sh` 中标记为废弃，并从主部署链路移除，当前由 diagnosis-agent 替代。以上脚本仅作为历史兼容和专项运维工具，不应随常规平台发布自动执行。

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
- [错误码系统](docs/error-code-system/README.md)
- [服务器运维说明](docs/ops/server-connection.md)
