# 下拉条统一改造设计文档

> 版本: v1.0 | 日期: 2026-06-12 | 状态: 设计阶段

---

## 一、现状分析

### 1.1 角色体系（后端）

```
UserCharacter 表字段:
  character:    0=组长, 1=软件开发, 2=软件应用, 3=应用, 4=算法
  is_nav_lead:  bool — 是否导航组组长
  is_servo_lead: bool — 是否对接组组长
  team_id:      "0"/"nav"=导航组, "1"/"servo"=对接组
```

**角色推导** (`auth/service.py → _derive_role_and_access`):

| character | is_nav_lead | is_servo_lead | → role | 可见范围 |
|-----------|-------------|---------------|--------|---------|
| 1/2/3/4 | false | false | **employee** | 仅自己 |
| 0 | **true** | false | **manager** (导航) | 导航组全员 |
| 0 | false | **true** | **manager** (对接) | 对接组全员 |
| 0 | **true** | **true** | **admin** | 全部 |

> `is_nav_lead + is_servo_lead` 仅在 `character=0` 时有意义

### 1.2 权限体系（前端）

| role | dataScope | 可见页面 | 首页 |
|------|-----------|---------|------|
| employee | `self` | 工时管理、绩效管理、AI助理 | 工时管理 |
| manager(nav) | `team` | 导航组详情 + 个人页x3 + 工作日耗时 | 导航组详情 |
| manager(servo) | `team` | 对接组详情 + 个人页x3 + 工作日耗时 | 对接组详情 |
| admin | `all` | 所有页面 | 部门总览 |

**Layout 分布**:

| 页面 | Layout | 谁在用 |
|------|--------|-------|
| 部门总览 | ManagerLayout | manager, admin |
| 导航组/对接组详情 | ManagerLayout | manager, admin |
| 工作日耗时 | ManagerLayout | manager, admin |
| 工时管理 | EmployeeLayout | 全员 |
| 绩效管理 | EmployeeLayout | 全员 |
| AI助理 | EmployeeLayout | 全员 |
| 权限管理 | ManagerLayout | admin |

### 1.3 当前下拉条分布（全页面审计）

| 页面 | 团队选择 | 人员选择 | 数据来源 | 团队值 |
|------|---------|---------|---------|-------|
| **PersonalHours** | 级联 `组→人` | 联动 | `/personal-hours/members` | `'导航组'` `'对接组'` `'其他'` |
| **PerformancePage** | ❌ | 平铺 `name·team` | `/performance-history`→memberOptions | — |
| **PerfImportModal** | 平铺下拉 | ❌ | **硬编码** `{nav,servo}` | `'nav'` `'servo'` |
| **TeamDetailDashboard** | ❌(页面即组) | 平铺名字数组 | API→memberOptions[].name | — |
| **DepartmentOverview** | ❌ | ❌ | — | — |
| **PermissionPage** | 平铺 | ❌ | 账户列表 team字段去重 | 账户原始值 |

### 1.4 核心不一致问题

| 问题 | 严重度 | 详情 |
|------|-------|------|
| **团队值三方命名** | 🔴高 | 前端硬编码 `'nav'/'servo'`，mock数据 `'导航组'/'对接组'`，后端DB `'0'/'1'` |
| **人员schema不统一** | 🔴高 | `{id,name,team}` vs `{userId,userName,isTeamLead}` vs 纯字符串数组 |
| **级联vs平铺** | 🟡中 | PersonalHours有级联，PerformancePage平铺混杂，PerfImportModal硬编码 |
| **无共用组件** | 🟡中 | 6个页面各自实现select，样式、逻辑完全不共享 |
| **PerfImportModal硬编码团队** | 🟡中 | 加新组需改前后端各一处 |

### 1.5 `is_nav_lead` / `is_servo_lead` 调用位置

```
后端使用（5处）:
├── auth/service.py:234-236    — 登录时推导角色（_derive_role_and_access）
├── auth/service.py:286-288    — 离线登录时推导角色
├── member_visibility.py:26-27  — is_dual_team_admin() 判断（用于隐藏管理员）
├── dashboard/__init__.py:53    — _member_role_label_from_user_character 参数（未实际使用）
└── workhour/team/routes.py:75  — 组长标记（character=0时跳过不统计）

前端使用：无直接引用，通过 user.role 间接使用
```

---

## 二、改造目标

### 2.1 目标架构

```
                    ┌─────────────────────────┐
                    │   unifiedTeamMemberApi   │  ← 统一后端API
                    │  /api/bt/perf/teams       │     返回团队列表
                    │  /api/bt/members?team=    │     返回成员列表
                    └───────────┬─────────────┘
                                │
                ┌───────────────┼───────────────┐
                ↓               ↓               ↓
        ┌───────────────┐ ┌──────────┐ ┌──────────────┐
        │ TeamSelector  │ │MemberSel │ │CascadeTeam   │
        │ (平铺选组)     │ │(平铺选人) │ │MemberSel     │
        └───────────────┘ └──────────┘ │(级联组→人)    │
                                       └──────────────┘
                ↓               ↓               ↓
        ┌───────────────────────────────────────────┐
        │  PerformancePage  PersonalHours  PerfImport │
        │  TeamDetailDash   PermissionPage  ...      │
        └───────────────────────────────────────────┘
```

### 2.2 分阶段实施

| 阶段 | 内容 | 影响范围 |
|------|------|---------|
| **Phase 1** | 统一数据模型 + 后端 API | 后端 |
| **Phase 2** | 抽出 `TeamSelector` / `MemberSelector` 通用组件 | 前端共用 |
| **Phase 3** | 改造各页面接入通用组件 | 6个页面逐一替换 |
| **Phase 4** | PerfImportModal 团队动态化 | 去掉硬编码 |

---

## 三、Phase 1: 统一数据模型

### 3.1 新增后端 API

**GET `/api/bt/perf/teams`** — 获取所有团队列表
```json
{
  "data": {
    "teams": [
      { "key": "nav",   "label": "导航组", "teamIds": ["nav","0","navigation"] },
      { "key": "servo", "label": "对接组", "teamIds": ["servo","1","service"] }
    ]
  }
}
```
> 数据来源：`UserCharacter.team_id` 的 DISTINCT 值 + 映射表

**GET `/api/bt/perf/members?team=nav`** — 按团队获取成员列表
```json
{
  "data": {
    "members": [
      { "userId": "u1", "userName": "张三", "team": "nav", "isTeamLead": false },
      { "userId": "u2", "userName": "李四", "team": "nav", "isTeamLead": true }
    ]
  }
}
```

### 3.2 统一 Schema

所有涉及"人员"的API返回统一下划线格式（前端映射为 camelCase）：

```
后端 → 前端
───────────────────
user_id  → userId
name     → userName
team_id  → teamKey
          → teamLabel    (导航组 / 对接组)
character → isTeamLead   (character==0)
is_nav_lead / is_servo_lead → 不外露
```

> **禁止**：`{id}` / `{userId}` / `{name}` / `{userName}` / `{isTeamLead}` / `{is_team_lead}` 在不同返回中混用

### 3.3 现有API兼容改造

| 现有 API | 当前字段 | 改造 |
|----------|---------|------|
| `/personal-hours/members` | `{id, name, team}` | 前端映射层一次转换 |
| `/performance-history` | `memberOptions[{id,name,team}]` | 后端加 `userId,userName,teamKey,teamLabel` |
| `/perf/team-import-users` | `{userId, userName, isTeamLead}` | 加 `teamKey, teamLabel`，**已接近目标** |

---

## 四、Phase 2: 通用组件设计

### 4.1 目录结构

```
src/components/selectors/
├── TeamSelector.jsx            # 平铺选组
├── MemberSelector.jsx          # 平铺选人
├── CascadeTeamMemberSelector.jsx # 级联组→人
└── index.js                     # 统一导出
```

### 4.2 TeamSelector

```tsx
interface TeamOption {
  key: string;      // 'nav' | 'servo'
  label: string;    // '导航组' | '对接组'
}

interface TeamSelectorProps {
  teams:       TeamOption[];
  value:       string | null;
  onChange:    (teamKey: string) => void;
  showAll?:    boolean;        // 是否显示"全部团队"
  placeholder?: string;
  className?:  string;
}
```

### 4.3 MemberSelector

```tsx
interface MemberOption {
  userId:     string;
  userName:   string;
  teamLabel?: string;         // 可选显示所属团队
  isTeamLead?: boolean;
}

interface MemberSelectorProps {
  members:    MemberOption[];
  value:      string | null;
  onChange:   (userId: string) => void;
  showAll?:   boolean;        // 是否显示"全部人员"
  showTeam?:  boolean;        // option 是否附加团队名（"张三 · 导航组"）
  className?: string;
}
```

### 4.4 CascadeTeamMemberSelector（级联）

```
┌──────────────┐  ┌──────────────────┐
│ 导航组    ▼  │  │ 张三 (组长) ▼    │
│ 对接组       │  │ 李四            │
│ 其他        │  │ 王五            │
└──────────────┘  └──────────────────┘
      选组后自动刷新 ↓
```

```tsx
interface CascadeTeamMemberSelectorProps {
  teams:          TeamOption[];
  membersByTeam:  Record<string, MemberOption[]>;  // teamKey → members
  teamValue:      string | null;
  memberValue:    string | null;
  onTeamChange:   (teamKey: string) => void;
  onMemberChange: (userId: string) => void;
}
```

---

## 五、Phase 3: 各页面替换方案

| 页面 | 替换为 | 代码减少 |
|------|-------|---------|
| **PerformancePage** | `<MemberSelector showTeam />` | ~8行 → 1个组件 |
| **PersonalHours** | `<CascadeTeamMemberSelector />` | ~40行 useMemo/useEffect → 1个组件 |
| **PerfImportModal** | `<TeamSelector />` (从API获取) | 去掉硬编码TEAMS |
| **TeamDetailDashboard** | `<MemberSelector showAll />` | ~10行 → 1个组件 |
| **PermissionPage** | `<TeamSelector showAll />` | ~5行 → 1个组件 |

---

## 六、Phase 4: 团队硬编码消除

### 6.1 当前硬编码点

**前端** `PerfImportModal.jsx`:
```js
const TEAMS = [
  { key: 'nav', label: '导航组' },
  { key: 'servo', label: '对接组' },
];
```

**后端** `performance/service.py`:
```python
_TEAM_ID_MAP = {
    "nav": {"nav", "0", "navigation"},
    "servo": {"servo", "1", "service", "对接", "servo_team"},
}
```

**后端** `auth/service.py`:
```python
def _team_name_from_team_id(team_id_value):
    if val == "0": return "导航组"
    if val == "1": return "对接组"
```

### 6.2 消除方案

1. 后端新增 `team_metadata` 表或从 `user_character.team_id` 动态生成
2. 前端 `PerfImportModal` 调用 `GET /perf/teams` 获取团队列表
3. 后端 `_TEAM_ID_MAP` 改为查询 `user_character` 的 team_id 去重 + 映射
4. 前端 `MemberSelector` 的 team 显示也统一取自 API

---

## 七、角色/界面切换规则（现状确认）

### 7.1 界面分布

```
角色           EmployeeLayout页          ManagerLayout页
─────────────────────────────────────────────────────────
employee       工时管理|绩效管理|AI助理     (无)
nav-manager    工时管理|绩效管理|AI助理     部门总览|导航组|工作日耗时
servo-manager  工时管理|绩效管理|AI助理     部门总览|对接组|工作日耗时
admin          工时管理|绩效管理|AI助理     全部页面
```

### 7.2 `canViewAllPeople` 判断（PerformancePage / PersonalHours 共用）

```js
const canViewAllPeople = user?.role === ROLES.MANAGER || user?.role === ROLES.ADMIN;
```

> ⚠️ **已知隐患**：nav-manager 下拉能看到 servo 组的人，实际靠 `dataScope=team` 在 mock 数据中过滤。真实API需要确保后端也做相应过滤。

### 7.3 跨组可见性矩阵

|                | nav-manager | servo-manager | admin |
|----------------|-------------|---------------|-------|
| 导航组成员     | ✅ dataScope 过滤 | ❌             | ✅ |
| 对接组成员     | ❌          | ✅            | ✅ |
| PerfImport可选组 | 全部(硬编码bug) | 全部(硬编码bug) | 全部 |

> PerfImportModal 硬编码了全部组，与 dataScope 不一致。改造后应由后端根据当前用户角色限制可见组。

---

## 八、实施优先级

1. **Phase 1** — 后端 `/perf/teams` + `/perf/members` 接口（影响最小，立即可用）
2. **Phase 2** — 抽出 3 个通用组件到 `src/components/selectors/`
3. **Phase 3** — 从 `PermissionPage` 开始逐页面替换，`PersonalHours` 最后
4. **Phase 4** — PerfImportModal 去硬编码 + 后端 `_TEAM_ID_MAP` 动态化
5. **未来** — `canViewAllPeople` 跨组可见性收紧（需配合后端 scope 过滤）
