# 后端组织名册与业务范围 V2 设计

> 版本：V2  
> 更新日期：2026-08-31  
> 状态：本地核心重构与自动化回归已完成，最新版本待服务器部署和真实业务验收  
> 适用项目：`management-system`

## 1. 文档结论

当前后端已经形成一个边界较清晰的**组织名册与业务人员范围模块**：

- 数据库 `user_character` 是运行期唯一人员数据源。
- `teamCode`、`jobRoleCode` 是新的稳定业务标识。
- Scope 统一表达“某项业务应该包含哪些团队、哪些岗位”。
- `base.organization.service` 是业务模块查询人员范围的统一入口。
- 组织 API 为前端团队和人员选择器提供统一数据。
- `ids.json` 只参与显式的一次性迁移，不再在应用启动时补人。

但它目前**不是完整的组织管理后台**。V2 负责“组织名册读取、范围判定和兼容迁移”，暂不负责人员增删改、在离职生命周期、历史调组、组织树和可视化 Scope 配置。

## 2. 设计目标

### 2.1 解决的问题

重构前，人员范围分散在以下位置：

- `user_character.team_id` 和 `character` 数字值；
- `ids.json` 人员配置；
- 后端 Python 人员白名单；
- 前端固定团队选项和中文名称判断；
- 各业务模块自行实现的人员过滤规则。

这导致同一个人可能在工时、出勤、绩效、应用组和同步任务中得到不同归属。V2 将“人员是谁、属于哪个正式团队、担任什么岗位、某业务应包含谁”收敛到一个模块中。

### 2.2 核心原则

1. **稳定编码优先**：业务判断使用 `teamCode` / `jobRoleCode`，中文名称只用于展示。
2. **数据库权威**：运行期不从静态文件自动恢复人员。
3. **策略集中**：业务人员范围由 Scope 声明，不在页面和任务中散落白名单。
4. **兼容收口**：公共 HTTP 契约和运行时业务只使用稳定编码；旧字段只由显式迁移命令解析。
5. **显式变更**：历史数据迁移必须由命令显式执行，应用启动只补列、不改组织归属。
6. **读取与管理分离**：当前模块提供稳定读取能力；人员维护能力以后独立设计。

## 3. 模块边界

### 3.1 V2 负责

- 正式团队、岗位、Scope 编码及展示名；
- 旧团队/岗位值的规范化；
- 从数据库读取组织名册；
- 按 Scope 和团队筛选人员；
- 为业务模块返回人员 ID 集合；
- 为前端返回统一团队和人员选项；
- 从 `ids.json` 到数据库的显式、幂等迁移与对账；
- 对外提供只含稳定组织字段的团队与人员 DTO。

### 3.2 V2 不负责

- 人员新增、编辑、删除 API 和管理页面；
- 在职、离职、借调等生命周期；
- 人员调组历史、生效时间和审计流水；
- 多团队成员关系或通用虚拟组织；
- 登录 RBAC、菜单权限和数据权限的统一建模；
- 数据库化、可视化的 Scope 策略管理；
- 组织主数据从钉钉自动同步。

其中认证仍由 `base.auth` 负责，菜单权限仍由现有权限体系负责；organization API 在登录会话基础上按 Scope 映射校验页面或操作权限。

## 4. 总体结构

```text
                      Frontend / Sync Job / Business Service
                                      │
                                      ▼
                         organization routes / service
                           │                    │
                           ▼                    ▼
                    Scope policy          code normalization
                           │                    │
                           └─────────┬──────────┘
                                     ▼
                         user_character (MySQL)
                                     ▲
                                     │ explicit only
                         organization.migration
                                     ▲
                                     │
                                  ids.json
```

代码结构：

```text
backend/base/organization/
├── __init__.py
├── constants.py    # 团队、岗位、兼容映射和 Scope 声明
├── scopes.py       # Scope 查询与合法性校验
├── service.py      # 名册读取、范围筛选和兼容 DTO
├── routes.py       # 登录保护的 organization HTTP API
└── migration.py    # 一次性迁移、dry-run、检查和人数验证
```

依赖方向为：

```text
业务模块 -> organization.service -> organization.scopes/constants
                                -> base.db

organization.routes -> organization.service
organization.migration -> organization.constants + base.db
```

`organization` 不依赖 `workhour`、`performance`、`application_team` 等上层业务模块。

## 5. 领域模型

### 5.1 正式团队

| `teamCode` | 展示名 | 旧存储 ID | 类型 |
|---|---|---:|---|
| `NAV` | 导航组 | `0` | 正式团队 |
| `INTEGRATION` | 对接组 | `1` | 正式团队 |
| `ALGORITHM` | 算法组 | `2` | 正式团队 |
| `APP_THREE` | 应用三组 | `3` | 正式团队 |

`teamCode` 是权威标识。旧数字 ID 只用于显式迁移和尚未完成物理字段迁移的内部存储，公共响应不再输出 `teamId`。

### 5.2 岗位

| `jobRoleCode` | 展示名 |
|---|---|
| `TEAM_LEAD` | 组长 |
| `SOFTWARE_ENGINEER` | 软件开发工程师 |
| `SOFTWARE_APPLICATION_ENGINEER` | 软件应用工程师 |
| `APPLICATION_ENGINEER` | 应用工程师 |
| `ALGORITHM_ENGINEER` | 算法工程师 |
| `INTERN` | 实习生 |
| `SYSTEM_ADMIN` | 管理员 |

岗位与登录角色不是同一个概念。`SYSTEM_ADMIN` 当前来自历史 `character=9` 的兼容映射；默认不属于无岗位限定的业务 Scope。

### 5.3 应用组

应用组不是正式团队，而是动态业务视图：

```text
team_code = NAV
AND job_role_code = APPLICATION_ENGINEER
```

因此应用工程师在部门工时、工作日耗时、出勤和绩效中仍归导航组；只有应用组相关业务通过 `APPLICATION_TEAM_VIEW` 筛选他们。

应用三组则是正式团队，必须显式配置：

```text
team_code = APP_THREE
```

两者不能通过 `team_id=3` 混用。

### 5.4 数据表

V2 渐进扩展 `user_character`：

| 字段 | 当前定位 |
|---|---|
| `user_id` | 人员主键，钉钉用户 ID |
| `name` | 展示姓名 |
| `team_code` | 权威团队编码 |
| `job_role_code` | 权威岗位编码 |
| `team_id` | 旧团队字段，仅供显式迁移和短期回滚审计 |
| `character` | 旧岗位字段，仅供显式迁移和短期回滚审计 |
| `is_nav_lead` / `is_servo_lead` / `is_p3_lead` | 三组主管权限标记，保留现有管理方式 |
| `union_id` | 钉钉身份关联字段，不属于组织范围策略 |

应用启动时 `base.db.engine` 可为旧环境增加缺失的 `team_code`、`job_role_code` 列，但不得自动回填字段值。

## 6. Scope 策略

Scope 是某个业务场景的人员集合策略，不是权限角色。

| Scope | 团队范围 | 岗位限制 | 消费方 |
|---|---|---|---|
| `DEPARTMENT_EFFECTIVE_HOURS` | NAV、INTEGRATION | 无 | 部门有效工时、团队详情 |
| `WORKDAY_COST` | NAV、INTEGRATION、ALGORITHM | 无 | 工作日耗时 |
| `ATTENDANCE` | NAV、INTEGRATION、ALGORITHM | 无 | 出勤 |
| `QUARTER_PERFORMANCE` | NAV、INTEGRATION | 无 | 季度绩效 |
| `APPLICATION_TEAM_VIEW` | NAV | APPLICATION_ENGINEER | 应用组报表 |
| `APP_THREE_TEAM_VIEW` | APP_THREE | 无 | 应用三组详情 |
| `TB_TASK_SYNC` | NAV、INTEGRATION | 无 | 本体团队 TB 同步 |

匹配顺序：

1. 规范化人员的团队和岗位编码；
2. 判断团队是否在 Scope 的 `teams` 中；
3. 若 Scope 声明 `roles`，继续判断岗位；
4. 无岗位限制时默认排除 `SYSTEM_ADMIN`；
5. 若调用方传入 `teamCode`，再做团队交集过滤。

新增团队或调整业务口径时，应先修改 Scope 策略及测试，再确认所有消费方的展示与汇总预期。业务代码不应额外叠加人员白名单。

## 7. 服务接口

`base.organization.service` 提供以下稳定入口：

```python
list_scope_teams(scope_code)
list_scope_members(scope_code, team_code=None, session_factory=None)
list_scope_member_ids(scope_code, team_code=None, session_factory=None)
is_person_in_scope(user_id, scope_code)
list_all_members(session_factory=None)
resolve_sync_operator_id(session_factory=None)
```

主要返回人员 DTO：

```json
{
  "userId": "ding-user-id",
  "userName": "张三",
  "teamCode": "NAV",
  "teamName": "导航组",
  "jobRoleCode": "APPLICATION_ENGINEER",
  "jobRoleName": "应用工程师",
  "isTeamLead": false
}
```

HTTP 路由会进一步白名单化字段，不对外输出 `isTeamLead`；公共成员响应固定为 `userId/userName/teamCode/teamName/jobRoleCode/jobRoleName`。

## 8. HTTP API

统一前缀为 `/api/bt`。接口既要求有效登录 Session，也按 Scope 校验对应页面或操作权限；不能只依赖前端菜单隐藏。

### 8.1 团队及人员选项

```http
GET /api/bt/organization/scopes/{scopeCode}/options
GET /api/bt/organization/scopes/{scopeCode}/options?teamCode=NAV
```

返回当前 Scope 的全部团队选项，以及可选团队过滤后的成员。团队选项会保留没有成员的团队，确保 UI 结构稳定。

### 8.2 人员列表

```http
GET /api/bt/organization/scopes/{scopeCode}/members
GET /api/bt/organization/scopes/{scopeCode}/members?teamCode=NAV
```

返回 `scopeCode`、`members` 和 `count`。

### 8.3 错误语义

| 场景 | HTTP 状态 |
|---|---:|
| 未登录 | 401 |
| Scope 或团队编码非法 | 400 |
| 数据库或服务异常 | 500 |

旧查询参数 `team` 不再参与过滤；调用方必须使用 `teamCode`。

## 9. 数据迁移

### 9.1 权威来源切换

```text
迁移前：ids.json + user_character + 代码白名单
迁移后：user_character
```

`ids.json` 仍可保存项目 ID，并可作为一次性人员迁移输入，但不再是运行期人员源。

### 9.2 历史 `team_id=3`

历史 `team_id=3` 表示旧应用组实验，并不等于现在的应用三组。显式迁移规则为：

```text
legacy team_id=3 -> team_code=NAV
                 -> job_role_code=APPLICATION_ENGINEER
```

真正的应用三组成员必须人工或通过明确数据源设置 `team_code=APP_THREE`。

### 9.3 命令

在 `backend` 目录执行：

```bash
PYTHONPATH=. python3 -m base.organization.migration --dry-run --verify
PYTHONPATH=. python3 -m base.organization.migration --apply --verify
PYTHONPATH=. python3 -m base.organization.migration --check --verify
```

- 默认和 `--dry-run`：只生成计划，不写数据库；
- `--apply`：显式执行；
- `--check`：存在待插入或待更新数据时返回非零；
- `--verify`：输出所有 Scope 人数。

迁移不会覆盖已经存在且可识别的稳定编码；重复执行应保持幂等。数据库中存在、但 `ids.json` 不存在的人员会保留。

## 10. 业务接入规则

新业务接入组织名册时：

1. 判断是否可复用已有 Scope；
2. 若业务范围不同，在 `SCOPE_POLICIES` 增加明确策略和测试；
3. 后端通过 `list_scope_members` 或 `list_scope_member_ids` 获取人员；
4. 前端通过 organization options API 获取团队与人员选项；
5. 业务数据返回 `teamCode`，名称只做展示；
6. 不新增人员 ID 白名单，不从 `ids.json` 读取运行期人员。

禁止模式：

```python
# 禁止：数字和中文展示值承载业务规则
if user.team_id != "2": ...
if row.team == "导航组": ...
if user_id in APPLICATION_USERS: ...
```

推荐模式：

```python
allowed_ids = list_scope_member_ids("APPLICATION_TEAM_VIEW")
```

## 11. 测试与当前验证状态

关键自动化测试：

- `test_scope_policies.py`：编码规范化和 Scope 矩阵；
- `test_roster_service.py`：人员筛选、应用组/应用三组歧义、迁移幂等；
- `test_organization_routes.py`：认证、参数和错误响应；
- 各工时、出勤、绩效、应用组和同步模块的业务回归测试。

截至 2026-08-31：

- 本地仓库完整后端测试：136 项通过；
- 前端 ESLint：0 error / 0 warning；
- 前端生产构建通过；
- `git diff --check` 通过。

以下服务器数据是较早版本的验收快照，不代表本轮最新代码已部署：migration 曾为 `insert=0, update=0, unchanged=24`，organization 定向测试曾有 29 项通过，服务健康检查曾为 HTTP 200。本轮最新接口契约和权限守卫仍需重新部署验证。

服务器当时的 Scope 人数：

| Scope | 人数 |
|---|---:|
| `DEPARTMENT_EFFECTIVE_HOURS` | 15 |
| `WORKDAY_COST` | 20 |
| `ATTENDANCE` | 20 |
| `QUARTER_PERFORMANCE` | 15 |
| `APPLICATION_TEAM_VIEW` | 4 |
| `APP_THREE_TEAM_VIEW` | 0 |
| `TB_TASK_SYNC` | 15 |

人数是部署验收快照，不是写死的设计值。应用三组当前无数据库成员，所以页面可正常打开但列表为空。

## 12. 已知限制与后续演进

### P0：完成业务验收

- 使用真实登录会话逐页验证工时、出勤、绩效、应用组和应用三组；
- 执行一次受控 TB 增量同步，确认 HTTP 成功、游标推进和锁释放；
- 配置真实 `APP_THREE` 成员后复核页面与 Scope 人数。

### P1：补齐管理能力

- 建设人员名册维护 API 和管理页；
- 继续补齐字段级输入校验和写操作审计日志；
- 增加 `employment_status`，让离职人员可保留历史数据但退出当前 Scope；
- 增加组织数据完整性约束，减少空编码和未知编码。

### P2：结束运行时兼容（已完成）

- 工时系数配置已切换为 `workhour_role_coefficients`，以 `jobRoleCode` 为键；
- `member_attendance` 新写入已使用 `team_code`；
- AI 工时工具、任务分析和运维脚本已不再读取 `team_id` / `character`；
- 旧值规范化函数只在 migration 边界使用，运行时只接受稳定编码；
- lead 布尔标记不删除；新增 `is_p3_lead` 后继续作为三组主管权限来源。
- 旧数据列暂不物理删除，待服务器数据回填、完整性校验和回滚窗口结束后单独 DDL 删列。
- 将 `RosterService` 的 Session 注入方式统一，避免模块级函数与 facade 两套调用风格并存。

### P3：策略平台化（按需要）

只有当 Scope 需要频繁由运营调整时，才将源码策略迁入数据库并建设管理页。届时必须增加版本、发布、审计和回滚机制，不能直接把未校验的数据库配置用于生产筛选。

## 13. 架构评价

V2 已经把原先分散的“人员白名单问题”转化为一个可测试的组织范围领域：编码稳定、数据源单一、规则集中、业务依赖方向清楚。这是当前规模下合适的后端结构。

运行时旧字段兼容已结束。下一阶段最重要的是完成真实业务验收、补上人员维护入口，并在回滚窗口结束后物理删除旧数据列。这些是从“清晰的名册读取内核”演进为“完整的组织管理能力”的后续管理能力，不再属于本次运行时重构。
