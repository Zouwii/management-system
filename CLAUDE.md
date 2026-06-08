# Management System (management-system)

## 项目概述

本体开发部数据管理平台。**数据驱动 · AI 驱动 · 研发效能提升**。

Flask 后端 + React (Vite) 前端，支持钉钉 OAuth 登录，集成 AI 任务分析和 Teambition 自动创建。

## 技术栈

- **后端**: Python 3.8+, Flask, SQLAlchemy 2.x, PyMySQL
- **前端**: React 19, Vite, Zustand, react-router-dom 7, TailwindCSS, Recharts
- **数据库**: MySQL（主库）+ pgvector / PostgreSQL（RAG 向量）+ SQLite（perf 库）
- **AI**: Claude CLI + MCP Server, LLM 任务分析, RAG 知识库检索
- **部署**: SSH 脚本部署到 `172.19.3.79`

## 目录结构

```
management-system/
├── debug-deploy.sh                 # 一键启动开发环境（后端+前端）
├── onekey-deploy.sh                # 一键打包+部署入口
├── scripts/
│   ├── 01-install-hooks.sh          # 安装 git pre-push hook
│   ├── 02-package.sh                # 构建前端+打包后端 tar.gz
│   ├── 03-deploy.sh                 # SSH 部署到服务器
│   └── 04-tag-package.sh            # git tag + 打包
├── pgvector-compose.yml             # pgvector 容器 (RAG 向量存储)
│
├── backend/                         # Flask 后端
│   ├── app.py                       # 薄封装 → base/app.py
│   ├── base/                        # ⭐ 基础设施层（v2 重构统一收敛）
│   │   ├── app.py                   #   create_app() + 3 daemon 线程
│   │   ├── api.py                   #   /api/bt 蓝图 + ok/fail 响应
│   │   ├── dingtalk_client.py       #   钉钉 OpenAPI 封装
│   │   ├── config.json              #   应用配置
│   │   ├── ids.json                 #   用户/项目 ID 映射
│   │   ├── db/                      #   SQLAlchemy ORM + session
│   │   ├── auth/                    #   OAuth/免登/session
│   │   ├── sync/                    #   数据同步（全量/增量）
│   │   ├── projects/                #   项目管理
│   │   ├── config/                  #   配置管理 + 工时自动计算
│   │   ├── stats/                   #   统计汇总
│   │   ├── health/                  #   健康检查/代理
│   │   └── route_registry/          #   统一路由注册
│   ├── ai/                          # AI 功能模块
│   │   ├── knowledge/               #   知识库子系统 (RAG)
│   │   ├── task_analysis/           #   任务分析栏
│   │   ├── tbcreate/                #   任务草稿创建
│   │   ├── teambition/              #   Teambition 任务创建
│   │   ├── terminal/                #   Claude CLI 交互终端
│   │   ├── mcp/                     #   MCP Server（独立进程）
│   │   ├── skills/                  #   LLM prompt 模板
│   │   ├── domain/                  #   领域规则
│   │   └── docs/                    #   AI 设计文档
│   ├── workhour/                    # 工时管理（personal/team）
│   ├── performance/                 # 绩效考核
│   ├── run_on_pc_daemon.sh          # 服务器守护进程
│   └── pyproject.toml               # Poetry 依赖管理
│
├── frontend-react/                  # React 前端源码
│   ├── src/
│   │   ├── pages/                   # 页面组件
│   │   ├── components/              # 通用组件
│   │   ├── api/                     # API 调用层 (providers: real/mock)
│   │   ├── store/                   # Zustand 状态管理
│   │   ├── router/                  # 路由 + 权限守卫
│   │   ├── layouts/                 # 布局组件
│   │   └── constants/               # 常量 (API mode 等)
│   ├── vite.config.js               # Vite 配置 (proxy /api/bt → :5001)
│   └── package.json
│
├── docs/                            # 架构文档
└── README.md
```

## 架构

v2 重构后采用 **base 核心包 + 功能模块** 的扁平化结构。

```
base/app.py (create_app + 3 daemon threads)
    │
    ├── base/api.py         → /api/bt 蓝图
    ├── base/route_registry/ → 统一注册所有模块路由
    ├── base/auth/           → 钉钉 OAuth 登录
    ├── base/sync/           → 数据同步
    ├── base/db/             → SQLAlchemy ORM
    │
    ├── ai/                  → AI 功能 (独立包，内聚 routes+service)
    ├── workhour/            → 工时管理 (personal/team)
    └── performance/         → 绩效考核
```

**3 个 daemon 线程**（在 `base/app.py` 中启动）：

| 线程 | 触发条件 | 功能 |
|------|----------|------|
| `_auto_calc_loop` | 配置时间点 | 自动触发工时计算 |
| `_auto_full_update_loop` | 每天 03:00 | 全量同步钉钉项目任务 |
| `_auto_knowledge_sync_loop` | 周一/四 04:00 + 每月 1 号 | 知识库大小同步 |

## 开发命令

### 后端
```bash
cd backend
python app.py                    # 启动后端（端口 5001，debug 默认开启）
```

### 前端
```bash
cd frontend-react
npm install                      # 安装依赖
npm run dev:real                 # Vite HMR 开发（端口 5173，代理 → :5001）
npm run mock                     # Mock 模式
npm run build                    # 构建，输出到 backend/static/react/
```

### 日常开发（一键启动）
```bash
./debug-deploy.sh
# 自动启动后端 :5001 + 前端 :5173
# Ctrl+C 同时关闭
```

### 日常开发（手动双终端）
```bash
# 终端 1
cd backend && python app.py

# 终端 2
cd frontend-react && npm run dev:real
# 访问 http://localhost:5173
```

## 钉钉登录

Vite dev server 通过 proxy 将 `/api/bt` 转发到 Flask `:5001`。

登录流程：
1. 前端 `GET /api/bt/auth/dingtalk/url` → 获取钉钉 OAuth 授权地址
2. 浏览器重定向到钉钉授权
3. 回调 `GET /api/bt/auth/callback` → Flask 建立 session
4. `GET /api/bt/auth/me` → 获取当前用户信息/角色

环境变量见 `backend/.env.example`：`DINGTALK_APPKEY`, `DINGTALK_APPSECRET`, `SECRET_KEY` 等。

## 部署

```bash
./onekey-deploy.sh              # 一键打包+部署到 172.19.3.79
# 或分步：
bash scripts/02-package.sh       # 构建前端 + 打包
bash scripts/03-deploy.sh        # SSH 部署
```

服务器守护进程（在服务器上）：
```bash
bash run_on_pc_daemon.sh start|stop|restart|status|logs
```

## 数据库

- **MySQL**: 项目任务、工时、用户角色、配置、锁 (`base/db/orm.py`)
- **pgvector/PostgreSQL**: 语义向量存储（`docker compose -f pgvector-compose.yml up -d`）
- **SQLite**: `performance/` 季度绩效考核数据

## 约定

- Python 函数使用 Google-style docstring（Args / Returns / Raises）
- import 路径相对于 `backend/`，如 `from base.sync.lock import ...`
- 钉钉 API 统一走 `base/dingtalk_client.py`
- 新增业务模块在 `base/route_registry/__init__.py` 注册路由
- AI 模块高度内聚，routes 和 service 可放同一目录下
- 前端 API 模式通过 `VITE_API_MODE` 环境变量切换 `real` / `mock`
- 前端 API 层 `providers/real/` 和 `providers/mock/` 双实现，通过 `createApiSwitch` 切换
