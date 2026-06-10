# 工作日耗时统计 业务文档

## 1. 概述

### 1.1 业务背景

`workday_costhour`（工作日耗时）是 Teambition 任务自定义字段，记录单个任务实际工作耗时，单位为**天**。系统通过定时同步将其写入 `project_task_details`、`project_task_overdue_details`、`program_issue_detail` 三张明细表，但缺少统一的多维度统计看板。

本模块为管理员提供按**任意时间范围**筛选的工作日耗时统计，从项目类型、车型、任务类型、小组等维度聚合展示。

### 1.2 权限

| 项目 | 内容 |
|------|------|
| 角色 | `admin`（管理员） |
| 数据范围 | 全部门（`dataScope: all`） |
| 菜单位置 | 左侧导航 → 部门 → 部门总览 → 工作日耗时统计 |

---

## 2. 模块架构

### 2.1 目录结构

```
backend/workhour/costhour/          # 独立业务模块
├── __init__.py                     # 模块说明
├── service.py                      # 核心查询 + 聚合逻辑（~350 行）
└── routes.py                       # 3 个 API 路由注册

backend/base/db/
├── orm.py                          # 明细表字段定义（project_category_1 等）
└── engine.py                       # 自动迁移逻辑

backend/base/sync/task_sync.py      # Teambition 同步 + 级联字段解析

backend/base/route_registry/
└── __init__.py                     # 路由注册入口（register_costhour）

frontend-react/src/
├── pages/WorkdayCostHourStats.jsx  # 页面主组件
├── api/dashboard.js                # API 函数注册
├── api/providers/real/dashboard.js # 真实 API 调用
├── api/providers/mock/dashboard.js # Mock 数据
├── constants/navigation.js         # 侧边栏菜单（部门总览 children）
├── constants/routes.js             # 路由路径
├── constants/permissionCodes.js    # 权限码
└── router/routeConfig.jsx          # 路由配置
```

### 2.2 模块依赖关系

```
┌─────────────────────────────────────────────────────────────┐
│                    前端 (React SPA)                         │
│  WorkdayCostHourStats                                       │
│    ├─ team_summary API                                      │
│    ├─ department_aggregate API                              │
│    └─ task_status_detail API                                │
└──────────────────────┬──────────────────────────────────────┘
                       │ POST /api/bt/stats/workday_costhour/*
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  workhour/costhour/routes.py   (3 个路由)                   │
└──────────┬──────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────┐
│  workhour/costhour/service.py  (查询 + 聚合)                │
│                                                             │
│  _query_workday_costhour_base()                             │
│    ├─ project_task_details (B 表)  ─→ 软件开发              │
│    ├─ project_task_overdue_details (C 表) ─→ 软件开发(去重) │
│    ├─ program_issue_detail         ─→ 问题处理              │
│    └─ user_character               ─→ 团队信息              │
│                                                             │
│  聚合函数:                                                  │
│    ├─ _aggregate_by_project_type()  → 产品/研发/订单        │
│    ├─ _aggregate_by_vehicle_type()  → 通用/AMR/叉车/...     │
│    └─ _aggregate_by_task_type()     → 软件开发/问题处理     │
└──────────────────────┬──────────────────────────────────────┘
                       │
           ┌───────────┼───────────┐
           ▼           ▼           ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────────┐
│ base/db/orm  │ │ base/sync/   │ │ base/route_      │
│ 三张明细表   │ │ task_sync    │ │ registry         │
│ + 级联字段   │ │ 解析写入     │ │ 路由注册         │
└──────────────┘ └──────────────┘ └──────────────────┘
```

---

## 3. 数据模型

### 3.1 数据表关系

```
┌────────────────────────────────────────────────────────┐
│                  project_tasks (A 表)                   │
│                  due_date (时间过滤)                    │
└──────┬─────────────────┬───────────────────┬───────────┘
       │ JOIN            │ JOIN              │ JOIN
       ▼                 ▼                   ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────────┐
│ project_task │ │ project_task │ │ program_issue_   │
│ _details     │ │ _overdue_    │ │ detail           │
│ (B 表)       │ │ details(C表) │ │                  │
│ 本季度排期   │ │ 逾期任务     │ │ 问题处理         │
│ → 软件开发   │ │ → 软件开发   │ │ → 问题处理       │
└──────┬───────┘ └──────┬───────┘ └────────┬─────────┘
       │                │                   │
       │ query_user_id  │ query_user_id     │ query_user_id
       ▼                ▼                   ▼
┌────────────────────────────────────────────────────────┐
│                  user_character                        │
│              user_id 关联 team_id                      │
│              team_id: 0=导航组, 1=对接组               │
└────────────────────────────────────────────────────────┘
```

### 3.2 明细表关键字段

| 字段 | 类型 | 来源 | 说明 |
|------|------|------|------|
| `workday_costhour` | FLOAT | TB 数值字段 | **核心度量**，单位：天 |
| `business_type` | INTEGER | TB 标签映射 | 0=产品, 1=研发, 2=订单 |
| `vehicle_type_2` | VARCHAR(128) | TB 级联字段 | 车型维度（通用/AMR/叉车/非标/重载/...） |
| `project_category_1` | VARCHAR(128) | TB 级联字段 | 项目分类（产品项目/研发项目/...） |
| `project_name_3` | VARCHAR(256) | TB 级联字段 | 具体项目名称 |
| `query_user_id` | VARCHAR(64) | TB executor | 执行者，关联 user_character |

### 3.3 Teambition 字段映射

| 维度 | TB 字段 | 映射方式 |
|------|---------|----------|
| 任务类型 | `scenarioFieldConfigId` | 常量匹配（软件开发 / 问题处理） |
| 项目类型 | `tagIds` | 标签映射表 `DEFAULT_BUSINESS_TYPE_TAG_MAPPING` |
| 车型 | `customFields[665ee4b...]` | 级联字段第 2 级 |
| 项目分类 | 同上 | 级联字段第 1 级 |
| 项目名称 | 同上 | 级联字段第 3 级 |
| 工作日耗时 | `customFields[64c8cad...]` | 数值字段 |
| 小组 | `user_character.team_id` | 0=导航组, 1=对接组 |

### 3.4 级联字段解析

```
Teambition 数据:
  customFieldId: "665ee4b45b46f34b3e045af2"
  type: "cascading"
  value: [{ title: "产品项目 / 通用 / 出厂流程优化" }]

解析规则（split by " / " + strip）:
  → project_category_1  = "产品项目"
  → vehicle_type_2      = "通用"
  → project_name_3      = "出厂流程优化"
```

### 3.5 B/C 表去重

同一 `task_id` 可能同时存在于 B 表和 C 表。去重策略：**B 表优先**，C 表中 task_id 已在 B 表出现的记录直接跳过。

### 3.6 度量定义

| 度量 | 计算 | 单位 |
|------|------|:--:|
| 工时 | `SUM(workday_costhour)` | 天 |
| 事项数 | `COUNT(*)` | 个 |

---

## 4. API 接口

Base: `POST /api/bt/stats/workday_costhour/`

### 4.1 通用参数

```json
{
  "start_time": "2025-07-01T00:00:00",
  "end_time":   "2025-09-30T23:59:59"
}
```

### 4.2 接口 1：`team_summary`

各小组明细数据汇总，按 team 分组展示项目类型、车型、任务类型三维度。

**响应结构**：
```json
{
  "timeRange": { "start_time": "...", "end_time": "..." },
  "total": { "hours": 530, "taskCount": 791 },
  "teams": [{
    "teamId": "0",
    "teamName": "导航组",
    "totalHours": 52,
    "totalCount": 30,
    "byProjectType": { "产品项目": {...}, "研发项目": {...}, ... },
    "byVehicleType":  { "通用": {...}, "AMR": {...}, ... },
    "byTaskType":     { "软件开发": {...}, "问题处理": {...} }
  }]
}
```

### 4.3 接口 2：`department_aggregate`

全部门聚合，不做团队拆分。返回项目类型、车型两个维度。

**响应结构**：
```json
{
  "timeRange": { "start_time": "...", "end_time": "..." },
  "total": { "hours": 530, "taskCount": 791 },
  "byProjectType": {
    "研发项目": { "hours": 103, "count": 76 },
    "产品项目": { "hours": 258, "count": 130 },
    "订单项目": { "hours": 130, "count": 70 }
  },
  "byVehicleType": {
    "通用": { "hours": 164, "count": 122 },
    "AMR":  { "hours": 37,  "count": 319 },
    ...
  }
}
```

### 4.4 接口 3：`task_status_detail`

按项目类型展开 → 软件开发/问题处理的层级明细。

**响应结构**：
```json
{
  "timeRange": { "start_time": "...", "end_time": "..." },
  "total": { "hours": 530, "taskCount": 791 },
  "details": [{
    "projectType": "研发项目",
    "totalHours": 103,
    "totalCount": 76,
    "children": [
      { "taskType": "软件开发", "hours": 87, "count": 68 },
      { "taskType": "问题处理", "hours": 16, "count": 8 }
    ]
  }],
  "summary": {
    "软件开发": { "hours": 471, "count": 255 },
    "问题处理": { "hours": 20,  "count": 21 },
    "totalHours": 530,
    "totalCount": 791
  }
}
```

---

## 5. 前端页面

### 5.1 路由配置

| 配置 | 值 |
|------|-----|
| 路径 | `/manager/workday-costhour` |
| 权限码 | `page.workday_costhour` |
| 角色 | admin |
| 侧边栏 | 部门 → 部门总览 → 工作日耗时统计（缩进子项） |

### 5.2 页面结构

```
┌─ 全局时间选择器 ───────────────────────────────────────┐
│  start_time / end_time                                 │
└────────────────────────────────────────────────────────┘

┌─ Section 1: 小组明细 ──────────────────────────────────┐
│  按 team 分组展示: 项目类型 | 车型 | 任务类型 三列卡片   │
└────────────────────────────────────────────────────────┘

┌─ Section 2: 部门级聚合 ────────────────────────────────┐
│  项目类型统计表          │  车型统计表                  │
└────────────────────────────────────────────────────────┘

┌─ Section 3: 任务状态明细 ───────────────────────────────┐
│  层级表格: 项目类型 → 软件开发/问题处理 → 汇总         │
└────────────────────────────────────────────────────────┘
```

### 5.3 数据流

```
用户选择时间范围
  → format start_time / end_time
  → Promise.all([ team_summary, department_aggregate, task_status_detail ])
  → 各自渲染 Section 1/2/3
```

---

## 6. 实现清单

### 6.1 后端

| 文件 | 说明 |
|------|------|
| `workhour/costhour/__init__.py` | 模块入口 |
| `workhour/costhour/service.py` | 核心查询(`_query_workday_costhour_base`) + 3 个聚合函数 + 3 个 service |
| `workhour/costhour/routes.py` | 3 个 `@bp.route(...)` 路由 |
| `base/route_registry/__init__.py` | `register_costhour(bp, ok, fail)` |
| `base/db/orm.py` | 3 张表各 +3 列 (`project_category_1`, `vehicle_type_2`, `project_name_3`) |
| `base/db/engine.py` | ALTER TABLE 自动迁移 |
| `base/sync/task_sync.py` | `_extract_cascading_project_fields()` + 6 个写入路径 |
| `base/stats/routes.py` | 移除了 costhour 路由（已迁至独立模块） |
| `workhour/personal/aggregate.py` | 移除了 costhour 相关函数（~420 行） |

### 6.2 前端

| 文件 | 说明 |
|------|------|
| `pages/WorkdayCostHourStats.jsx` | 主页面（ManagerLayout + 3 个 Section） |
| `pages/DepartmentOverview.jsx` | 部门总览页面 |
| `components/SideMenu.jsx` | 支持 children 子菜单渲染 |
| `layouts/ManagerLayout.jsx` | children 传递 + 角色过滤 |
| `layouts/EmployeeLayout.jsx` | 同上 |
| `constants/navigation.js` | 工作日耗时统计作为部门总览子项 |
| `constants/routes.js` | `WORKDAY_COSTHOUR` 路由 |
| `constants/permissionCodes.js` | `page.workday_costhour` 权限码 |
| `router/routeConfig.jsx` | 路由配置 |
| `api/dashboard.js` | 3 个 API 注册 |
| `api/providers/real/dashboard.js` | 真实 API |

---

## 7. 扩展方向

### 7.1 项目名称维度
`project_name_3` 已入库，后续可增加按项目名称过滤/聚合。

### 7.2 小组扩展
新增小组只需在 `_team_name_static() ` 添加 team_id 映射，接口自动按 team_id 分组。

### 7.3 数据导出
三张表格均可增加 CSV/Excel 导出功能。
