# 本体开发部数据平台

基于 React + Vite + Tailwind CSS 的前端项目，面向“本体开发部数据平台”原型的持续开发。当前代码已经不是单纯骨架，而是包含角色登录、权限控制、主管端组织视图、员工端个人视图，以及 mock / real 双请求模式的一版可运行前端。

本轮代码扫视结论：

- 当前仓库仍保持清晰的前端单仓结构，主链路为 `main -> router -> guards/layout -> pages -> api -> providers(mock/real)`
- 权限与首页跳转逻辑集中在 `constants + utils/permission + router/guards`，没有明显出现页面内各自散落判断的失控情况
- mock 数据、真实接口适配和页面展示层边界基本清楚，暂未发现阻塞交付的结构性问题
- 已本地验证 `npm run lint` 与 `npm run build` 均通过

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
src
├── api
│   ├── auth.js
│   ├── client.js
│   ├── dashboard.js
│   ├── request.js
│   └── providers
│       ├── mock
│       └── real
├── components
├── constants
├── layouts
├── mock
├── pages
├── router
├── store
└── utils
```

说明：

- `src/pages` 按页面拆分，不同界面由不同文件管理
- `src/components` 放通用组件和跨页面复用结构
- `src/layouts` 放主管端 / 员工端布局
- `src/api/providers/mock` 与 `src/api/providers/real` 分别对应 mock 数据源和真实接口

## 架构分层

项目当前可以按 6 层理解：

1. `src/main.jsx` / `src/App.jsx`
   应用启动入口，仅负责挂载 React 和路由容器。
2. `src/router`
   负责路由注册、根路径跳转、公开页/受保护页分流，以及页面权限拦截。
3. `src/layouts`
   负责主管端、员工端的导航壳层和角色视图差异，不承担业务数据拼装。
4. `src/pages`
   负责页面级状态、查询参数、数据请求触发和业务展示组合。
5. `src/api`
   负责统一 API 入口和 `mock` / `real` provider 切换，避免页面直接感知数据源。
6. `src/mock` + `src/utils` + `src/constants`
   负责样例数据、领域常量、权限码、数据范围和展示转换等基础支撑。

这种组织方式的好处是：

- 页面层只关心“拿什么数据、怎么展示”
- provider 层只关心“数据从哪里来、返回什么结构”
- 权限、首页、菜单等横切规则集中维护，后续继续扩展页面时不容易失控

## 主运行链路

最核心的运行路径如下：

1. [`src/main.jsx`](/home/wuhaoxian/body-dev-data-platform/src/main.jsx) 挂载 `BrowserRouter`
2. [`src/router/index.jsx`](/home/wuhaoxian/body-dev-data-platform/src/router/index.jsx) 根据配置生成公开路由与受保护路由
3. [`src/router/guards.jsx`](/home/wuhaoxian/body-dev-data-platform/src/router/guards.jsx) 结合登录态、角色和权限码决定是否放行或重定向
4. [`src/layouts/ManagerLayout.jsx`](/home/wuhaoxian/body-dev-data-platform/src/layouts/ManagerLayout.jsx) / [`src/layouts/EmployeeLayout.jsx`](/home/wuhaoxian/body-dev-data-platform/src/layouts/EmployeeLayout.jsx) 根据角色生成菜单和端侧说明
5. 页面通过 [`src/api/dashboard.js`](/home/wuhaoxian/body-dev-data-platform/src/api/dashboard.js) / [`src/api/auth.js`](/home/wuhaoxian/body-dev-data-platform/src/api/auth.js) 发起统一请求
6. [`src/api/client.js`](/home/wuhaoxian/body-dev-data-platform/src/api/client.js) 根据 `VITE_API_MODE` 切到 `mock` 或 `real` provider

这条链路当前比较顺，没有发现页面直接绕过统一 API 层去操作底层数据源的明显反模式。

## 页面与路由

当前主要路由定义在 [`src/router/routeConfig.jsx`](/home/wuhaoxian/body-dev-data-platform/src/router/routeConfig.jsx) 和 [`src/constants/routes.js`](/home/wuhaoxian/body-dev-data-platform/src/constants/routes.js)。

| 页面 | 路径 | 说明 |
| --- | --- | --- |
| 登录页 | `/login` | 登录与注册入口 |
| 部门总览 | `/manager/department-overview` | 主管端组织级总览 |
| 导航组详情 | `/manager/nav-team-detail` | 主管端团队详情 |
| 对接组详情 | `/manager/integration-team-detail` | 主管端团队详情 |
| 个人工时页 | `/employee/personal-hours` | 员工端主工作台，主管/管理员也可查看 |
| 绩效页 | `/employee/performance` | 个人绩效历史 |
| AI 分析页 | `/employee/ai-analysis` | AI 建议与分析 |
| 权限管理 | `/manager/permissions` | 权限矩阵和说明，仅管理员可见 |
| 原型整页 | `/prototype` | 仅管理员可见 |

## 运行方式

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

相关定义见 [`src/constants/api.js`](/home/wuhaoxian/body-dev-data-platform/src/constants/api.js)。

## mock 账号

mock 登录通过账号密码映射到具体用户，当前演示账号如下：

| 账号 | 密码 | 角色 |
| --- | --- | --- |
| `employee` | `123456` | 员工 |
| `navManager` | `123456` | 主管（导航组） |
| `servoManager` | `123456` | 主管（对接组） |
| `admin` | `123456` | 管理员 |

对应 mock 用户信息见 [`src/mock/auth.js`](/home/wuhaoxian/body-dev-data-platform/src/mock/auth.js)。

说明：

- `manager` 是角色类型，不是当前可登录的 mock 账号
- 当前主管账号拆成 `navManager` 和 `servoManager`，分别落到不同团队首页

## 权限模型

当前项目实现了三层权限控制：

- 页面权限码：控制路由可访问性
- 按钮权限码：控制页面内具体操作按钮
- 数据范围权限：控制用户可见数据范围

核心文件：

- [`src/constants/permissionCodes.js`](/home/wuhaoxian/body-dev-data-platform/src/constants/permissionCodes.js)
- [`src/constants/permissions.js`](/home/wuhaoxian/body-dev-data-platform/src/constants/permissions.js)
- [`src/router/guards.jsx`](/home/wuhaoxian/body-dev-data-platform/src/router/guards.jsx)
- [`src/components/PermissionButton.jsx`](/home/wuhaoxian/body-dev-data-platform/src/components/PermissionButton.jsx)

### employee

- 可见页面：工时管理、绩效管理、AI 分析中心
- 数据范围：本人
- 默认首页：个人工时页

### manager

- 可见页面：部门总览、导航组详情、对接组详情、工时管理、绩效管理、AI 分析中心
- 数据范围：本人 + 团队 + 部门
- 典型按钮权限：导出报表、查看 AI 建议、点评成员

### admin

- 可见页面：全部页面
- 数据范围：全部
- 按钮权限：全部

## 请求层说明

统一 API 入口：

- [`src/api/auth.js`](/home/wuhaoxian/body-dev-data-platform/src/api/auth.js)
- [`src/api/dashboard.js`](/home/wuhaoxian/body-dev-data-platform/src/api/dashboard.js)

底层能力：

- [`src/api/client.js`](/home/wuhaoxian/body-dev-data-platform/src/api/client.js) 负责真实 HTTP 请求和 mock / real 切换
- [`src/api/request.js`](/home/wuhaoxian/body-dev-data-platform/src/api/request.js) 负责 mock 模式下的异步延迟模拟

切换规则：

- `mock` 模式调用 `src/api/providers/mock/*`
- `real` 模式调用 `src/api/providers/real/*`

### 当前 dashboard 接口约定

- `GET /dashboard/department-overview`
- `GET /dashboard/nav-team-detail`
- `GET /dashboard/integration-team-detail`
- `GET /dashboard/personal-hours?target=...`
- `POST /dashboard/personal-hours/query`
- `POST /dashboard/personal-hours/update`
- `GET /dashboard/performance-history?target=...`
- `GET /dashboard/ai-insights`
- `POST /dashboard/ai-task-ticket`
- `GET /dashboard/permission-matrix`

## 个人工时页说明

个人工时页对应 [`src/pages/PersonalHours.jsx`](/home/wuhaoxian/body-dev-data-platform/src/pages/PersonalHours.jsx)，是当前功能最完整的一页，也是最适合优先对接后端的一页。

当前前端已支持：

- 默认按当前登录角色决定查看范围
- 主管 / 管理员可切换查看对象
- 时间区间查询
- 调休天数输入
- 查询与更新动作分离
- 月度趋势、任务分布、任务明细筛选

当前结构特点：

- 页面展示口径使用“天”，底层 mock 统计仍保留 `hours` 作为基础字段
- 查询和更新动作分离，便于后端后续分别接入“试算”和“落库”接口
- `target` 参数模式已在个人工时和绩效页面复用，后续扩展组织级查询时可以继续沿用

## 绩效页说明

[`src/pages/PerformancePage.jsx`](/home/wuhaoxian/body-dev-data-platform/src/pages/PerformancePage.jsx)

当前已支持：

- 基于当前登录用户加载季度绩效历史
- 主管 / 管理员按可见范围切换查看对象
- 展示最终绩效、结余绩效和季度变化口径
- mock / real provider 均支持按 `target` 查询

## AI 助理页说明

[`src/pages/AIAnalysisPage.jsx`](/home/wuhaoxian/body-dev-data-platform/src/pages/AIAnalysisPage.jsx)

当前已支持：

- 拉取 AI 建议列表
- 根据建议创建任务单草稿
- 为后续对接真实任务系统预留 `ai-task-ticket` 接口

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

[`src/pages/DepartmentOverview.jsx`](/home/wuhaoxian/body-dev-data-platform/src/pages/DepartmentOverview.jsx)

当前已实现：

- 组织视图切换
- 团队 / 风险范围切换
- 组织负载分布
- 风险观察卡片
- 管理动作建议
- 人员明细筛选表格

### 团队详情

[`src/pages/NavTeamDetail.jsx`](/home/wuhaoxian/body-dev-data-platform/src/pages/NavTeamDetail.jsx)
[`src/pages/IntegrationTeamDetail.jsx`](/home/wuhaoxian/body-dev-data-platform/src/pages/IntegrationTeamDetail.jsx)

团队详情页已抽出共享结构：

- [`src/components/TeamDetailDashboard.jsx`](/home/wuhaoxian/body-dev-data-platform/src/components/TeamDetailDashboard.jsx)

共享能力包括：

- 视图控制
- 任务构成展示
- 成员变化趋势
- 风险观察
- 主管建议
- 明细筛选表格

### 共享表格

[`src/components/TeamTable.jsx`](/home/wuhaoxian/body-dev-data-platform/src/components/TeamTable.jsx)

当前支持：

- 关键词搜索
- 风险筛选
- 绩效筛选
- 工天 / 有效率排序
- 展开全部 / 收起

## 数据单位说明

当前项目中的底层工时数据仍以“小时”存储和计算，但界面展示统一转换为“天”。

转换工具：

- [`src/utils/workHours.js`](/home/wuhaoxian/body-dev-data-platform/src/utils/workHours.js) 中的 `formatDays`

这意味着：

- 前端显示统一为“天”
- 接口和 mock 数据内部仍可能继续使用 `hours` 字段
- 后端对接时需要明确基础计量单位，避免展示和接口口径不一致

## 当前开发建议

- 个人工时页优先对接真实后端
- 后端先稳定个人工时相关接口字段和统计口径
- 部门总览与团队页继续沿用统一的分析页风格优化
- 后续如果扩展组织级接口，建议复用个人工时页的时间范围和目标对象参数模式

## 本轮检查记录

本次对代码层次和结构做了快速扫视，关注点主要是入口、路由守卫、布局、权限模型、统一 API 层，以及 mock/real provider 的职责边界。

检查结果：

- 未发现阻塞提交的结构性问题
- 权限页当前已经收敛为仅管理员可访问，和路由、菜单、权限说明保持一致
- 默认首页跳转已改为基于完整 `user` 对象计算，可兼容自定义 `homePath`
- 页面命名、菜单文案和角色侧边栏分区比早期版本更统一

本地验证命令：

```bash
npm run lint
npm run build
```
