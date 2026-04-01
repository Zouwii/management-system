# 本体开发部数据平台前端骨架

## 项目说明

这是一个基于 React + Vite + Tailwind CSS 的前端骨架项目，面向“本体开发部数据平台”原型继续工程化开发。

当前项目已经具备以下能力：

- 页面拆分：部门总览、导航组详情、对接组详情、个人工时、绩效、AI 分析、权限管理、登录页
- 布局拆分：主管端布局、员工端布局
- 通用组件拆分：统计卡片、侧边菜单、表格、标题等
- 路由管理：React Router
- 状态管理：Zustand
- 权限骨架：角色权限、页面权限、按钮权限、数据范围权限
- 请求层骨架：mock / real 双 provider 切换
- mock 登录：账号密码映射角色，不在登录页面直接暴露身份

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
│   ├── providers/mock
│   └── providers/real
├── components
├── constants
├── layouts
├── mock
├── pages
├── router
├── store
└── utils
```

## 启动方式

安装依赖：

```bash
npm install
```

本地 mock 模式启动：

```bash
npm run mock
```

访问地址：

```text
http://localhost:5173/login
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

## 环境变量

当前支持：

- `VITE_API_MODE`
  可选值：`mock`、`real`
- `VITE_API_BASE_URL`
  真实接口模式下的接口前缀，默认 `/api`

## mock 登录说明

登录页面只保留“登录”和“注册”入口，不直接显示角色。

当前 mock 环境使用以下演示账号：

| 账号 | 密码 | 角色 |
| --- | --- | --- |
| `employee` | `123456` | 员工 |
| `manager` | `123456` | 主管 |
| `admin` | `123456` | 管理员 |

注册入口当前仅预留前端骨架，真实注册逻辑待后端接口接入。

## 角色权限说明

### employee

- 可见页面：工时管理、绩效管理、AI分析中心
- 可见数据范围：本人数据
- 不可访问：部门总览、导航组详情、对接组详情、权限管理

### manager

- 可见页面：部门总览、导航组详情、对接组详情、个人工时页、绩效页、AI分析页、权限管理页
- 可见数据范围：本人 + 所管组 + 部门数据
- 可用按钮权限：导出报表、查看 AI 建议、点评成员

### admin

- 可见页面：全部页面
- 可见数据范围：全部数据
- 可用按钮权限：全部按钮权限

## 权限模型

项目当前实现了三层权限骨架：

- 页面权限码
  用于控制路由守卫和页面访问
- 按钮权限码
  用于控制具体操作按钮是否显示
- 数据范围权限
  用于控制 mock 数据返回范围

主要权限定义文件：

- `src/constants/permissionCodes.js`
- `src/constants/permissions.js`
- `src/router/guards.jsx`
- `src/components/PermissionButton.jsx`

## 请求层说明

请求层已抽象为统一 API 入口，页面不直接依赖 mock 数据文件。

当前结构：

- `src/api/auth.js`
- `src/api/dashboard.js`
- `src/api/client.js`
- `src/api/providers/mock/*`
- `src/api/providers/real/*`

切换逻辑：

- `mock` 模式走本地 mock provider
- `real` 模式走真实 HTTP 请求

后续接后端时，优先补齐：

- `/auth/login`
- `/auth/register`
- `/dashboard/department-overview`
- `/dashboard/nav-team-detail`
- `/dashboard/integration-team-detail`
- `/dashboard/personal-hours`
- `/dashboard/performance-history`
- `/dashboard/ai-insights`
- `/dashboard/permission-matrix`

## 当前状态

当前版本的目标是作为“可持续开发的前端骨架”，重点解决：

- 页面结构清晰
- 权限边界清晰
- mock 与真实接口切换清晰
- 后续继续扩展时不需要推翻现有结构
