# Real 模式缺失 API 清单

> 日期: 2026-06-12 | 每个前端调用都列出了对应后端接口及实现状态

---

## 一、完全缺失（返回 404）

这些 API 前端在用，但后端没有任何路由。

### 1. `GET /api/dashboard/department-overview`

**前端**: `realFetchDepartmentOverview` → `httpRequest('/dashboard/department-overview')`

**使用页面**: `DepartmentOverview.jsx`

**期望返回**:
```json
{
  "stats": {
    "totalMembers": 10,
    "navMembers": 4,
    "integrationMembers": 6,
    "totalHours": 1200
  },
  "rows": [{ "name": "张三", "team": "导航组", "hours": 156, ... }],
  "lastUpdatedAt": "2026-06-12T10:00:00Z"
}
```

**建议实现**: 新建 `backend/base/route_registry/dashboard/department_overview.py`，聚合 nav + servo 两组 `user_character` + 当前季度工时数据。

---

### 2. `GET /api/dashboard/ai-insights`

**前端**: `realFetchAIInsightList` → `httpRequest('/dashboard/ai-insights')`

**使用页面**: `AIAnalysisPage.jsx`

**期望返回**:
```json
{
  "insights": [
    { "id": "1", "title": "...", "type": "risk", "createdAt": "..." }
  ]
}
```

**建议**: 如暂不需要，先返回空数组。

---

### 3. `GET /api/dashboard/permission-matrix`

**前端**: `realFetchPermissionMatrix` → `httpRequest('/dashboard/permission-matrix')`

**使用页面**: `PermissionPage.jsx`

**期望返回**:
```json
[
  { "userId": "u1", "userName": "张三", "password": "123456", "role": "employee", "roleLabel": "员工", "team": "导航组", "permissionCodes": [...] }
]
```

**建议实现**: 从 `user_character` 表 + `auth/service.py` 的角色推导逻辑生成。

---

## 二、Performance 相关（刚新增，需后端重启加载）

以下接口代码已写好，但 Flask 需重启才能生效。

| 接口 | 方法 | 用途 |
|------|------|------|
| `/api/bt/perf/teams` | GET | 团队列表 |
| `/api/bt/perf/members?team=` | GET | 统一成员列表 |
| `/api/bt/perf/update-quarter-member` | POST | 全字段更新绩效 |

> **操作**: 重启 Flask 即可。

---

## 三、现有但需验证

这些接口后端有路由，但需确认返回格式与前端预期一致。

| 接口 | 前端调用 | 需确认 |
|------|---------|-------|
| `/api/dashboard/personal-hours` | `realFetchPersonalHours` | 返回 `{dashboard, trend, memberOptions, lastUpdatedAt}` |
| `/api/dashboard/personal-hours/members` | `realFetchPersonalHoursMembers` | 返回 `{memberOptions: [{id, name, team, ...}]}` |
| `/api/dashboard/personal-hours/query` | `realQueryPersonalHours` | POST，body 含 startDate/endDate/target |
| `/api/dashboard/performance-history` | `realFetchPerformanceHistory` | GET，query 含 target |
| `/api/dashboard/nav-team-detail` | `realFetchNavTeamDetail` | 接收 expected 参数 |
| `/api/dashboard/integration-team-detail` | `realFetchIntegrationTeamDetail` | 同上 |
| `/api/bt/perf/query` | — (无前端调用) | 已实现 |
| `/api/bt/perf/team-import-users` | `realFetchTeamImportUsers` | GET，query 含 year/quarter/team |
| `/api/bt/perf/batch-import` | `realBatchImportScores` | POST，body 含 year/quarter/team/members |

---

## 四、优先实施顺序

| 优先级 | 接口 | 原因 |
|--------|------|------|
| 🔴 P0 | `/dashboard/department-overview` | 部门总览完全不可用 |
| 🔴 P0 | `/dashboard/permission-matrix` | 权限管理页不可用 |
| 🟡 P1 | `/perf/teams`, `/perf/members`, `/perf/update-quarter-member` | 重启 Flask 即可 |
| 🟢 P2 | `/dashboard/ai-insights` | AI 页面用，可先空实现 |
