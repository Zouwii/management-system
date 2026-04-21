# Management System (management-system)

## 项目概述

内部管理系统，包含 **Flask 后端** 和 **React (Vite) 前端**。当前正在将前后端合并到同一个服务中部署（`feat/merge_front_and_end` 分支）。

## 技术栈

- **后端**: Python 3.8+, Flask, SQLAlchemy 2.x, PyMySQL, python-dotenv
- **前端**: React 19, Vite, Zustand, react-router-dom 7, TailwindCSS
- **数据库**: MySQL（主库）+ SQLite（perf 库）
- **部署**: Docker, docker-compose

## 目录结构

```
management-system/
├── backend/                 # Flask 后端（当前工作目录）
│   ├── app.py              # Flask app 入口，create_app()
│   ├── api.py              # API 蓝图
│   ├── dashboard_api.py    # Dashboard 蓝图
│   ├── db/
│   │   ├── config.py       # 数据库配置（从 .env 读取）
│   │   ├── engine.py       # SQLAlchemy engine & session
│   │   └── orm.py          # ORM 模型定义
│   ├── route_registry/     # 路由模块（每个文件一个 Blueprint）
│   │   ├── route_index.py  # URL -> 处理函数 -> service 映射索引
│   │   ├── auth.py         # 认证相关
│   │   ├── stats.py        # 统计
│   │   └── ...
│   ├── services/           # 业务逻辑层
│   ├── models/             # 数据模型
│   ├── static/react/       # 前端构建产物（merge 分支后 serve 这里）
│   ├── config.json         # 应用配置
│   └── pyproject.toml      # Poetry 依赖管理
├── frontend-react/         # React 前端源码
│   ├── src/
│   │   ├── pages/          # 页面组件
│   │   ├── components/     # 通用组件
│   │   ├── api/            # API 调用层
│   │   ├── store/          # Zustand 状态管理
│   │   ├── router/         # 路由配置
│   │   └── layouts/        # 布局组件
│   └── package.json
└── docker-compose.yml
```

## 开发命令

### 后端
```bash
# 在 backend/ 目录下
poetry install              # 安装依赖
poetry run python app.py    # 启动后端
# 或
bash run_on_pc.sh           # 本地运行脚本
```

### 前端
```bash
# 在 frontend-react/ 目录下
npm install
npm run dev                 # 开发模式 (port 5173)
npm run dev:real            # 连接真实后端
npm run build               # 构建，产物输出到 backend/static/react/
```

## 架构约定

- **路由层** (`route_registry/`): 注册 Blueprint，处理 HTTP 请求/响应
- **服务层** (`services/`): 业务逻辑，被路由层调用
- **数据层** (`db/`): SQLAlchemy ORM 模型和数据库会话管理
- 前端构建后产物放在 `backend/static/react/`，由 Flask 直接 serve
- 数据库连接配置通过 `.env` 文件管理，由 `db/config.py` 读取
- API 模式：前端 `api/providers/` 下分 `real/` 和 `mock/` 两套

## 注意事项

- urllib3 锁在 < 2，因为旧 WSL/Ubuntu 的 OpenSSL 版本较低
- SQLAlchemy 使用 scoped_session 处理 Flask 多线程
- 中文日历相关功能使用 `chinese-calendar` 和 `chinese-workday`

- 所有返回的对话以#zhr_start开头，以#zhr_end为结尾