# 团队、岗位与业务人员范围重构计划

> 日期：2026-08-28  
> 状态：历史实施计划；运行时稳定字段切换已在本地完成，最新版本待服务器部署、迁移复核与真实页面验收  
> 适用项目：`management-system`

> 当前设计请以 [后端组织名册与业务范围 V2 设计](./organization-backend-v2-design.md) 为准。本文保留作为重构背景、批次和决策记录。

## 1. 背景

当前系统同时使用 `user_character.team_id`、`character`、`ids.json`、Python 人员白名单和前端固定团队选项表达人员范围。不同页面各自维护过滤规则，已经出现以下问题：

- 工作日耗时、出勤表和应用组分别维护人员 ID 白名单。
- 绩效、部门有效工时和前端下拉框各自解释 `team_id`。
- 应用组既被部分代码当成 `team_id=3`，又被部分代码当成导航组四人白名单。
- `ids.json` 与数据库同时成为人员源，启动时可能把已从数据库删除的人重新补回。
- 中文团队名称和数字 ID 被直接用于业务判断，增加团队时容易漏改。

本次重构的核心是建立统一的团队、岗位和业务人员范围（Scope）模型，让所有后端业务和前端下拉框通过同一个 `RosterService` 取人。

## 2. 已确认的业务规则

### 2.1 正式团队

| 编码 | 名称 | 说明 |
|---|---|---|
| `NAV` | 导航组 | 正式团队 |
| `INTEGRATION` | 对接组 | 正式团队 |
| `ALGORITHM` | 算法组 | 正式团队 |
| `APP_THREE` | 应用三组 | 额外的正式团队 |

### 2.2 应用组定义

应用组不是虚拟团队，也不是独立的正式团队。它是一个动态人员视图：

```text
team_code = NAV
AND job_role_code = APPLICATION_ENGINEER
```

应用工程师在有效工时、工作日耗时、出勤和绩效中仍归属导航组；只有应用组问题分析页使用上述岗位条件取人。

### 2.3 业务 Scope 矩阵

| Scope 编码 | 业务页面/任务 | 团队范围 | 额外岗位条件 |
|---|---|---|---|
| `DEPARTMENT_EFFECTIVE_HOURS` | 部门有效工时 | `NAV`, `INTEGRATION` | 无 |
| `WORKDAY_COST` | 工作日耗时 | `NAV`, `INTEGRATION`, `ALGORITHM` | 无 |
| `ATTENDANCE` | 出勤表 | `NAV`, `INTEGRATION`, `ALGORITHM` | 无 |
| `QUARTER_PERFORMANCE` | 季度绩效 | `NAV`, `INTEGRATION` | 无 |
| `APPLICATION_TEAM_VIEW` | 应用组报表 | `NAV` | `APPLICATION_ENGINEER` |
| `APP_THREE_TEAM_VIEW` | 应用三组详情 | `APP_THREE` | 无 |
| `TB_TASK_SYNC` | 本体团队 TB 同步 | `NAV`, `INTEGRATION` | 无 |

## 3. 本次范围和明确不做项

### 3.1 本次要做

- 统一团队和岗位编码。
- 建立集中式 Scope 策略定义。
- 建立 `RosterService` 及统一团队/人员接口。
- 迁移有效工时、工作日耗时、出勤表、季度绩效、应用组和 TB 同步。
- 增加应用三组。
- 统一前端下拉框数据源。
- 停止 `ids.json` 在运行期自动补人。

### 3.2 本次不做

- 不做在职/离职状态。
- 不做人员管理页。
- 不做人员删除 API。
- 不做人员历史调组和生效日期。
- 不建虚拟组及多团队成员关系。
- 不合并导航/对接两张季度绩效表。
- 不开发 Scope 管理页；第一版 Scope 策略放在后端集中配置中。

人员增删改后续使用独立运维脚本处理，不阻塞本次架构重构。

## 4. 目标数据模型

### 4.1 `user_character` 渐进式扩展

第一阶段不立即删除旧字段，增加：

```text
team_code       VARCHAR(64)
job_role_code   VARCHAR(64)
```

保留：

- `team_id` / `character`：仅供显式迁移和短期回滚审计，运行时业务不再读取。
- `is_nav_lead` / `is_servo_lead` / `is_p3_lead`：分别作为导航组、对接组、应用三组主管权限来源。

### 4.2 编码映射

```text
team_id=0 -> NAV
team_id=1 -> INTEGRATION
team_id=2 -> ALGORITHM
```

历史 `team_id=3` 曾表示旧应用组，不能在运行期直接解释为应用三组。
显式迁移将旧 `team_id=3` 转为 `NAV + APPLICATION_ENGINEER`；真正的应用三组人员必须显式设置 `team_code=APP_THREE`。

```text
character=0 -> TEAM_LEAD
character=1 -> SOFTWARE_ENGINEER
character=2 -> SOFTWARE_APPLICATION_ENGINEER
character=3 -> APPLICATION_ENGINEER
character=4 -> ALGORITHM_ENGINEER
character=5 -> INTERN
```

`character=9` 属于当前管理员/访客兼容值，第一阶段不应自动迁移为普通业务岗位；由 Scope 策略默认排除。

### 4.3 人员数据源

- 运行期唯一人员源为数据库 `user_character`。
- `ids.json` 只作为存量迁移来源，不再在每次启动时补全人员。
- `projectids` 本次可继续保留在 `ids.json`，不与人员重构捆绑。

## 5. 目标代码结构

```text
backend/base/organization/
├── __init__.py
├── constants.py       # 团队、岗位、Scope 编码和展示名
├── scopes.py          # 集中式 Scope 策略声明
├── service.py         # RosterService
├── routes.py          # 团队/人员统一 API
└── migration.py       # 显式存量数据迁移与对账
```

`RosterService` 至少提供：

```python
list_scope_teams(scope_code)
list_scope_members(scope_code, team_code=None)
list_scope_member_ids(scope_code, team_code=None)
is_person_in_scope(user_id, scope_code)
```

统一 API：

```text
GET /api/bt/organization/scopes/{scopeCode}/options
GET /api/bt/organization/scopes/{scopeCode}/members
GET /api/bt/organization/scopes/{scopeCode}/members?teamCode=NAV
```

业务代码不得再根据中文团队名、数字 `team_id` 或人员 ID 白名单判断人员范围。

## 6. 分批实施计划

### 6.1 批次一：架构底座

#### 开发内容

- 增加团队、岗位和 Scope 常量。
- 增加 `team_code` / `job_role_code` 字段及无迁移工具环境下的自动补列逻辑。
- 编写存量数据回填脚本，支持 dry-run、执行和对账。
- 实现 `RosterService` 和统一 API。
- 增加 Scope 矩阵测试和 RosterService 单元测试。
- 第一批不切换现有业务，先对比新旧人员集合。

#### 主要涉及文件

- `backend/base/db/orm.py`
- `backend/base/db/engine.py`
- `backend/base/organization/*`
- `backend/base/route_registry/*`
- `backend/tests/test_scope_policies.py`
- `backend/tests/test_roster_service.py`

#### 验收

- 每个 Scope 的团队集合与本文矩阵一致。
- 应用组只返回导航组的应用工程师。
- 新 API 不影响现有页面和同步。

批次一迁移命令（在 `backend` 目录执行）：

```bash
PYTHONPATH=. python3 -m base.organization.migration --dry-run
PYTHONPATH=. python3 -m base.organization.migration --apply --verify
```

应用启动不再自动从 `ids.json` 补人；`ids.json` 仅由上述一次性命令读取。

预计：1.5～2.5 人天。

### 6.2 批次二：工作日耗时和出勤（已完成）

#### 开发内容

- 删除 `WHITELIST_USER_IDS`。
- 删除 `ATTENDANCE_APPLICATION_USER_IDS` 及导航/对接/算法分组白名单。
- 工作日耗时使用 `WORKDAY_COST` Scope。
- 出勤表使用 `ATTENDANCE` Scope。
- 保留主任务库和算法任务库的不同数据源，但用 Roster 统一决定参与人员。
- 出勤表从 Roster 补全当季度无任务数据的人员。
- 前端工作日耗时和出勤团队下拉改为读取 Scope API。

#### 主要涉及文件

- `backend/workhour/costhour/service.py`
- `backend/workhour/costhour/attendance.py`
- `frontend-react/src/pages/WorkdayCostHourStats.jsx`
- `frontend-react/src/pages/AttendancePage.jsx`
- 新增相关 Scope 测试

#### 验收

- 工作日耗时和出勤均显示导航、对接、算法。
- 应用工程师在两个页面中归导航组。
- 应用三组不会默认混入。
- 没有任务数据的 Scope 成员仍出现在出勤表。

预计：2～3 人天。

### 6.3 批次三：部门有效工时和季度绩效（已完成）

#### 开发内容

- 部门总览、导航详情、对接详情统一使用 `DEPARTMENT_EFFECTIVE_HOURS`。
- 人数来自 Roster，不再用“有任务数据的人数”推导。
- 季度绩效团队和人员选项使用 `QUARTER_PERFORMANCE`。
- 删除绩效服务中通过 `team_id != 2` 和团队别名表示范围的逻辑。
- 本次保留导航/对接两张绩效表，仅重构人员选择入口。
- 前端绩效导入弹窗和主页使用 Scope API。

#### 主要涉及文件

- `backend/base/department/service.py`
- `backend/workhour/team/routes.py`
- `backend/workhour/personal/routes.py`
- `backend/performance/service.py`
- `frontend-react/src/pages/DepartmentOverview.jsx`
- `frontend-react/src/pages/QuarterlyEffectivePerformancePage.jsx`
- `frontend-react/src/components/TeamDetailDashboard.jsx`
- `frontend-react/src/components/PerfImportModal.jsx`

#### 验收

- 有效工时和季度绩效只包含导航、对接。
- 算法组和应用三组不出现。
- 应用工程师正常归属导航组。
- 迁移前后导航/对接工时总值和绩效记录数不发生意外变化。

预计：1.5～2.5 人天。

### 6.4 批次四：应用组和应用三组（已完成）

#### 开发内容

- 删除 `APPLICATION_TEAM_USER_IDS`。
- 删除应用组对 `team_id=3` 和四人兼容名单的依赖。
- 应用组报表通过 `APPLICATION_TEAM_VIEW` 取人。
- 建立应用三组正式团队配置和人员数据。
- 增加应用三组路由、菜单和权限代码。
- 如应用三组指标与导航/对接一致，复用 `TeamDetailDashboard`；如数据源不同，保留独立 service，但人员范围仍必须来自 Scope。

#### 主要涉及文件

- `backend/application_team/report_service.py`
- `backend/application_team/routes.py`
- `backend/workhour/team/routes.py`
- `frontend-react/src/constants/navigation.js`
- `frontend-react/src/constants/routes.js`
- `frontend-react/src/constants/permissionCodes.js`
- `frontend-react/src/router/routeConfig.jsx`
- 应用组/应用三组页面和测试

#### 验收

- 导航组人员的岗位改为 `APPLICATION_ENGINEER` 后自动进入应用组。
- 岗位改回后自动退出应用组。
- 应用三组人员不会被应用组规则选中。
- “应用组”和“应用三组”的菜单、路由和数据互不串扰。

预计：1～1.5 人天。

### 6.5 批次五：TB 同步、前端统一与收尾（开发已完成）

#### 开发内容

- `_load_allowed_executor_ids()` 改为调用 `TB_TASK_SYNC` Scope。
- TB 主同步仅取导航和对接，算法保留独立同步链路。
- （已在批次一完成）移除启动时从 `ids.json` 自动补人的逻辑。
- 增加“数据库删除人员后重启不恢复”回归测试。
- 通过统一 organization Scope API 为相关团队和人员下拉提供数据。
- 将本次涉及的人员下拉统一到 Scope API。
- 删除前端 `teamId === '0'`、`row.team === '导航组'` 等业务判断。
- 补齐 Mock provider 与真实 API provider 的统一数据结构。
- 进行完整数据对账、部署和真实同步验证。

#### 验收

- TB 同步成员数与 `TB_TASK_SYNC` Scope 一致。
- 所有团队和人员下拉来自统一 API。
- 中文团队名只用于展示。
- 数据库人员不会被 `ids.json` 在重启时恢复。
- 生产真实增量同步成功，游标推进，锁正常释放。

预计：2～3 人天。

## 7. 测试矩阵

| 人员类型 | 部门有效工时 | 工作日耗时 | 出勤 | 季度绩效 | 应用组 | TB 主同步 |
|---|---:|---:|---:|---:|---:|---:|
| 导航软件工程师 | 是 | 是 | 是 | 是 | 否 | 是 |
| 导航应用工程师 | 是 | 是 | 是 | 是 | 是 | 是 |
| 对接工程师 | 是 | 是 | 是 | 是 | 否 | 是 |
| 算法工程师 | 否 | 是 | 是 | 否 | 否 | 否 |
| 应用三组人员 | 否 | 否 | 否 | 否 | 否 | 否 |
| 管理员/访客兼容账号 | 否 | 否 | 否 | 否 | 否 | 否 |

如应用三组未来需要进入工作日耗时或出勤，只修改对应 Scope 策略及测试矩阵，不修改页面业务代码。

## 8. 数据迁移和对账

### 8.1 迁移脚本必须支持

```text
--dry-run       只输出计划变更（默认行为）
--apply         显式执行迁移
--check         检查漂移；需要变更时返回非零退出码
--verify        输出各 Scope 人数，可与上述参数组合
```

除“新团队编码为空且旧 `team_id=3`”这一已确认歧义需要纠正岗位外，脚本不得覆盖已经手工维护的非空新字段；重复执行必须幂等。

### 8.2 上线前对账

- 各正式团队人数。
- 各 Scope 人数和人员清单。
- 应用组现有人员是否都映射为导航 + 应用工程师。
- 导航/对接有效工时总值。
- 导航/对接/算法工作日耗时总值。
- 出勤人数和已保存调整数。
- 季度绩效记录数。
- TB 同步成员数。

## 9. 部署策略

采用兼容式分批上线，不做一次性切换：

1. 上线新字段、Scope 和 RosterService，旧业务暂不切换。
2. 在生产数据副本上运行迁移 dry-run 和对账。
3. 切换工作日耗时和出勤。
4. 切换有效工时和绩效。
5. 切换应用组并上线应用三组。
6. 最后切换 TB 同步并关闭 `ids.json` 人员回填。
7. 执行真实增量同步，验证 HTTP 200、游标推进和锁释放。

每个批次都必须能独立测试和回退。

## 10. 工作量估算

| 批次 | 工作量 |
|---|---:|
| 架构底座 | 1.5～2.5 人天 |
| 工作日耗时与出勤 | 2～3 人天 |
| 有效工时与季度绩效 | 1.5～2.5 人天 |
| 应用组与应用三组 | 1～1.5 人天 |
| TB 同步、前端统一与收尾 | 2～3 人天 |
| 数据迁移、测试与部署缓冲 | 2～3 人天 |

合计约 11～15 人天。在自动化搜索、批量重构和测试生成辅助下，可以争取在 7～10 个集中工作日内完成，但生产数据对账和真实同步验证不应压缩。

## 11. 开发入口（历史记录）

开发从批次一开始，首个可交付里程碑为：

1. 新建 `backend/base/organization/`。
2. 定义团队、岗位和 Scope 常量。
3. 完成 `RosterService` 及单元测试。
4. 提供统一 options/members API。
5. 运行新旧人员集合对比，不立即改动现有页面。

批次一验收后，再开始删除业务模块中的白名单和固定团队判断。
