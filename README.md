# 本体开发部数据平台

仓库内 **React** 前端位于 `frontend-react/`（与 `frontend-vue/`、`backend/` 并列）。基于 React + Vite + Tailwind CSS，面向“本体开发部数据平台”原型的持续开发。当前代码已经不是单纯骨架，而是包含角色登录、权限控制、主管端组织视图、员工端个人视图，以及 mock / real 双请求模式的一版可运行前端。

## 当前实现

- 登录与注册入口
- 角色区分：员工、主管、管理员
- 页面级权限、按钮级权限、数据范围权限
- 员工端页面：工时管理、绩效管理、AI 分析中心
- 主管端页面：部门总览、导航组详情、对接组详情、权限管理
- 主管端和员工端分离布局
- `mock` / `real` 双 provider 请求层
- 个人工时页支持按查看对象切换、时间区间查询、更新动作
- 部门总览和团队页已升级为分析型页面结构，支持筛选、排序和下钻导航

## 技术栈

- React 19
- Vite 8
- Tailwind CSS 3
- React Router DOM 7
- Zustand 5

## 目录结构

```text
frontend-react/
├── src
│   ├── api
│   │   ├── auth.js
│   │   ├── client.js
│   │   ├── dashboard.js
│   │   ├── request.js
│   │   └── providers
│   │       ├── mock
│   │       └── real
│   ├── components
│   ├── constants
│   ├── layouts
│   ├── mock
│   ├── pages
│   ├── router
│   ├── store
│   └── utils
├── public
├── index.html
├── package.json
└── vite.config.js
```

说明：

- `frontend-react/src/pages` 按页面拆分，不同界面由不同文件管理
- `frontend-react/src/components` 放通用组件和跨页面复用结构
- `frontend-react/src/layouts` 放主管端 / 员工端布局
- `frontend-react/src/api/providers/mock` 与 `frontend-react/src/api/providers/real` 分别对应 mock 数据源和真实接口

## 页面与路由

当前主要路由定义在 [`frontend-react/src/router/routeConfig.jsx`](frontend-react/src/router/routeConfig.jsx) 和 [`frontend-react/src/constants/routes.js`](frontend-react/src/constants/routes.js)。

| 页面 | 路径 | 说明 |
| --- | --- | --- |
| 登录页 | `/login` | 登录与注册入口 |
| 部门总览 | `/manager/department-overview` | 主管端组织级总览 |
| 导航组详情 | `/manager/nav-team-detail` | 主管端团队详情 |
| 对接组详情 | `/manager/integration-team-detail` | 主管端团队详情 |
| 个人工时页 | `/employee/personal-hours` | 员工端主工作台，主管/管理员也可查看 |
| 绩效页 | `/employee/performance` | 个人绩效历史 |
| AI 分析页 | `/employee/ai-analysis` | AI 建议与分析 |
| 权限管理 | `/manager/permissions` | 权限矩阵和说明 |
| 原型整页 | `/prototype` | 仅管理员可见 |

## 运行方式

进入 React 子项目目录：

```bash
cd frontend-react
```

安装依赖：

```bash
npm install
```

本地 mock 模式启动：

```bash
npm run mock
```

或：

```bash
npm run dev
```

指定 5173 端口并监听所有地址：

```bash
npm run dev:5173
```

真实接口模式启动：

```bash
npm run dev:real
```

构建：

```bash
npm run build
```

代码检查：

```bash
npm run lint
```

本地安装 Git hooks（让 IDE 打 tag 并 push 时自动执行打包脚本）：

```bash
./scripts/01-install-hooks.sh
```

默认访问地址：

```text
http://localhost:5173/login
```

## 环境变量

当前支持以下环境变量：

- `VITE_API_MODE`
  可选值：`mock`、`real`
- `VITE_API_BASE_URL`
  真实接口模式下的接口前缀，默认值为 `/api`

相关定义见 [`frontend-react/src/constants/api.js`](frontend-react/src/constants/api.js)。

后端钉钉登录（Flask Session）相关环境变量见 `backend/.env.example`，关键项：

- `DINGTALK_APPKEY` / `DINGTALK_APPSECRET`
- `DINGTALK_CORP_ID`（可选；也可放在 `backend/config.json` 的 `corpId`）
- `DINGTALK_REDIRECT_URI`（例如 `http://localhost:5001/api/bt/auth/callback`）
- `SECRET_KEY`
- `SESSION_COOKIE_SAMESITE`、`SESSION_COOKIE_SECURE`
- `SESSION_EXPIRE_SECONDS`
- `CORS_ORIGINS`

## 钉钉登录（real 模式）

当 `VITE_API_MODE=real` 时，登录页使用钉钉 OAuth 登录，不再走账号密码。

后端认证接口：

- `GET /api/bt/auth/dingtalk/url`：获取钉钉授权地址，同时返回 `corpId/clientId`（供 `dd.requestAuthCode` 使用）
- `GET /api/bt/auth/callback`：钉钉回调，建立服务端会话
- `POST /api/bt/auth/get_token`：钉钉内免登，`dd.requestAuthCode` 拿到 `code` 后 POST `{ "code": "...", "clientId": "..." }`（`clientId` 可选，等于 `appKey`），成功后设置 Session Cookie 并返回 `data.user`
- `GET /api/bt/auth/me`：获取当前会话用户
- `POST /api/bt/auth/logout`：登出并销毁会话

说明：登录时若钉钉用户信息未返回 `userid`，后端会自动调用 `getUseridByUnionid` 补齐，再按 `userid` 查询 `user_character`，并将解析后的 `team/teamId/role` 缓存到会话里。

权限映射配置：

- 文件：`backend/auth_mapping.json`
- 作用：把钉钉用户标识（优先 `unionId`，其次 `openId/userid`）映射到系统角色与权限
- 迁移策略：当前是“静态映射兜底”；后续可接入 DB RBAC，代码预留在 `backend/services/auth_service.py`

## mock 账号

mock 登录通过账号密码映射角色，当前演示账号如下：

| 账号 | 密码 | 角色 |
| --- | --- | --- |
| `employee` | `123456` | 员工 |
| `manager` | `123456` | 主管 |
| `admin` | `123456` | 管理员 |

对应 mock 用户信息见 [`frontend-react/src/mock/auth.js`](frontend-react/src/mock/auth.js)。

## 权限模型

当前项目实现了三层权限控制：

- 页面权限码：控制路由可访问性
- 按钮权限码：控制页面内具体操作按钮
- 数据范围权限：控制用户可见数据范围

核心文件：

- [`frontend-react/src/constants/permissionCodes.js`](frontend-react/src/constants/permissionCodes.js)
- [`frontend-react/src/constants/permissions.js`](frontend-react/src/constants/permissions.js)
- [`frontend-react/src/router/guards.jsx`](frontend-react/src/router/guards.jsx)
- [`frontend-react/src/components/PermissionButton.jsx`](frontend-react/src/components/PermissionButton.jsx)

### employee

- 可见页面：工时管理、绩效管理、AI 分析中心
- 数据范围：本人
- 默认首页：个人工时页

### manager

- 可见页面：部门总览、导航组详情、对接组详情、工时管理、绩效管理、AI 分析中心、权限管理
- 数据范围：本人 + 团队 + 部门
- 典型按钮权限：导出报表、查看 AI 建议、点评成员

### admin

- 可见页面：全部页面
- 数据范围：全部
- 按钮权限：全部

## 请求层说明

统一 API 入口：

- [`frontend-react/src/api/auth.js`](frontend-react/src/api/auth.js)
- [`frontend-react/src/api/dashboard.js`](frontend-react/src/api/dashboard.js)

底层能力：

- [`frontend-react/src/api/client.js`](frontend-react/src/api/client.js) 负责真实 HTTP 请求和 mock / real 切换
- [`frontend-react/src/api/request.js`](frontend-react/src/api/request.js) 负责 mock 模式下的异步延迟模拟

切换规则：

- `mock` 模式调用 `frontend-react/src/api/providers/mock/*`
- `real` 模式调用 `frontend-react/src/api/providers/real/*`

### 当前 dashboard 接口约定

- `GET /dashboard/department-overview`
- `GET /dashboard/nav-team-detail`
- `GET /dashboard/integration-team-detail`
- `GET /dashboard/personal-hours?target=...`
- `POST /dashboard/personal-hours/query`
- `POST /dashboard/personal-hours/update`
- `GET /dashboard/performance-history`
- `GET /dashboard/ai-insights`
- `GET /dashboard/permission-matrix`

## 个人工时页说明

个人工时页对应 [`frontend-react/src/pages/PersonalHours.jsx`](frontend-react/src/pages/PersonalHours.jsx)，是当前功能最完整的一页，也是最适合优先对接后端的一页。

当前前端已支持：

- 默认按当前登录角色决定查看范围
- 主管 / 管理员可切换查看对象
- 时间区间查询
- 调休天数输入
- 查询与更新动作分离
- 月度趋势、任务分布、任务明细筛选

mock / real provider 当前都已经支持以下调用方式：

- `fetchPersonalHours(user, { target })`
- `queryPersonalHours(user, payload)`
- `updatePersonalHours(user, payload)`

其中 `payload` 主要包含：

- `startDate`
- `endDate`
- `compensatoryDays`
- `target`

## 主管端页面说明

### 部门总览

[`frontend-react/src/pages/DepartmentOverview.jsx`](frontend-react/src/pages/DepartmentOverview.jsx)

当前已实现：

- 组织视图切换
- 团队 / 风险范围切换
- 组织负载分布
- 风险观察卡片
- 管理动作建议
- 人员明细筛选表格

### 团队详情

[`frontend-react/src/pages/NavTeamDetail.jsx`](frontend-react/src/pages/NavTeamDetail.jsx)
[`frontend-react/src/pages/IntegrationTeamDetail.jsx`](frontend-react/src/pages/IntegrationTeamDetail.jsx)

团队详情页已抽出共享结构：

- [`frontend-react/src/components/TeamDetailDashboard.jsx`](frontend-react/src/components/TeamDetailDashboard.jsx)

共享能力包括：

- 视图控制
- 任务构成展示
- 成员变化趋势
- 风险观察
- 主管建议
- 明细筛选表格

### 共享表格

[`frontend-react/src/components/TeamTable.jsx`](frontend-react/src/components/TeamTable.jsx)

当前支持：

- 关键词搜索
- 风险筛选
- 绩效筛选
- 工天 / 有效率排序
- 展开全部 / 收起

## 数据单位说明

当前项目中的底层工时数据仍以“小时”存储和计算，但界面展示统一转换为“天”。

转换工具：

- [`frontend-react/src/utils/workHours.js`](frontend-react/src/utils/workHours.js) 中的 `formatDays`

这意味着：

- 前端显示统一为“天”
- 接口和 mock 数据内部仍可能继续使用 `hours` 字段
- 后端对接时需要明确基础计量单位，避免展示和接口口径不一致

## 当前开发建议

- 个人工时页优先对接真实后端
- 后端先稳定个人工时相关接口字段和统计口径
- 部门总览与团队页继续沿用统一的分析页风格优化
- 后续如果扩展组织级接口，建议复用个人工时页的时间范围和目标对象参数模式
