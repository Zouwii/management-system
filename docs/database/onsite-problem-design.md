# onsite_problem 数据库设计说明

本文描述 **现场问题跟踪项目**（Teambition projectId: `616e6868a46ec51df166f4cd`）的持久化设计，沿用 `project_tasks` 的 A/B 表模式。

---

## 1. customField 定义

基于两个示例任务的 API 返回数据定义。

### 1.1 基础模板（共用字段）

| cfId | type | 业务含义 | 示例值 |
|------|------|----------|--------|
| `659369d32ae435dd0b3c803e` | cascading | **车型** | `EMMA标车 / K系列 / 1000K` |
| `637c2e2ffbb56c003fdd74e9` | dropDown | **载具配置** | `不带载具` |
| `62c51d82d7ab965fbdebd686` | dropDown | **复现概率** | `单车偶现` / `单车必现` |
| `6645bd4d22e1f70dadb953f6` | dropDown | **JZTOTAL包版本** | `2.2311` / `＜2.2309` |
| `624e4bf0972b3d03d3008c4c` | text | **问题描述** | `中科磁业 7.18 11:40:39 导航过程中...` |
| `69241440caabefe748f91359` | rtf | **排查结论** | `无` / `111` |
| `692414313ffb7e9afc4e9f43` | dropDown | **排查文档价值** | `无相关参考文档——转给应用工程师后...` |
| `6924139133e26574155ea68b` | lookup2 | **排查文档** | `无【通用】` / `海康车网线连接网段配置` |
| `625f75e9882430143f5bfd0a` | work | **其他附件信息** | 6个附件(截图/视频/bag/log) / csv |

### 1.2 扩展模板（额外字段）

| cfId | type | 业务含义 | 示例值 |
|------|------|----------|--------|
| `691a95544ce9d3d5a5e541e1` | cascading | **问题类型分类** | `本体导航 / 控制` |
| `691a95f304c9e52bc9058bd6` | dropDown | **问题模块分类** | `本体导航` |
| `62651eadef4cf6063244aa5c` | lookup | **指导文档** | `1，快速入门和基础讲解` |
| `625f8339882430143f5c0b9a` | text | **正式版本** | `1.2412` |
| `625f8317d472ef3d5c2f39a4` | text | **原因分析** | `12333` |
| `625f8329b416f5118bb099b2` | text | **解决方案** | `456` |
| `68f637359ae2d0854e946cb3` | text | **提交者** | `邹宏睿` |

---

## 2. 设计目标

| 业务 | 数据来源 | 持久化目标 |
|------|-----------|------------|
| **A：任务列表** | `GET /v1.0/project/users/{userId}/projectIds/{projectId}/tasks` | 定期同步，全量 upsert |
| **B：任务明细** | `GET /v1.0/project/users/{userId}/tasks?taskId=…` | 逐条拉取，解析常用 customField 拆列，其余存 raw_json |

---

## 3. 表一览

| 表名 | 别名 | 说明 |
|------|------|------|
| `onsite_problem_tasks` | **A 表** | 列表快照（顶层字段 + raw_json） |
| `onsite_problem_details` | **B 表** | 明细快照（解析关键 customField + raw_json 兜底） |

**数据库**：独立库 `onsite_problem`

---

## 4. 项目配置

| 配置项 | 值 |
|--------|-----|
| projectId | `616e6868a46ec51df166f4cd` |
| scenarioFieldConfigId | `616e686948312307a5a9f994` |
| taskListId | `6937b84737c9f29fc1c7e684` |

---

## 5. 表 `onsite_problem_tasks`（A 表）

### 5.1 列定义

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INTEGER | PK, 自增 | |
| `project_id` | VARCHAR(64) | NOT NULL | |
| `task_id` | VARCHAR(64) | NOT NULL | |
| `content` | TEXT | | 任务标题 |
| `scenario_field_config_id` | VARCHAR(64) | | 模板 ID |
| `stage_id` | VARCHAR(64) | | |
| `task_list_id` | VARCHAR(64) | | |
| `task_stage_id` | VARCHAR(64) | | |
| `taskflow_status_id` | VARCHAR(64) | | 工作流状态 |
| `executor_id` | VARCHAR(64) | | 执行者 |
| `creator_id` | VARCHAR(64) | | 创建者 |
| `due_date` | DATETIME | NULL | 截止时间 |
| `start_date` | DATETIME | NULL | 开始时间 |
| `ding_created` | DATETIME | NULL | 钉钉 `created` |
| `ding_updated` | DATETIME | NULL | 钉钉 `updated` |
| `note` | TEXT | | 备注 |
| `priority` | INTEGER | DEFAULT 0 | |
| `progress` | INTEGER | DEFAULT 0 | |
| `visible` | VARCHAR(32) | | 可见范围 |
| `is_archived` | BOOLEAN | DEFAULT false | |
| `is_deleted` | BOOLEAN | DEFAULT false | |
| `is_done` | BOOLEAN | DEFAULT false | |
| `ancestor_ids` | JSON | NULL | |
| `involve_members` | JSON | NULL | |
| `tag_ids` | JSON | NULL | |
| `labels` | JSON | NULL | |
| `customfield_ids` | JSON | NULL | 仅存 customFieldId 数组 |
| `raw_json` | TEXT | NULL | 完整列表行 JSON |
| `list_synced_at` | DATETIME | NULL | |

**唯一约束**：`UNIQUE (project_id, task_id)`

---

## 6. 表 `onsite_problem_details`（B 表）

### 6.1 基础字段

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INTEGER | PK, 自增 | |
| `project_id` | VARCHAR(64) | NOT NULL | |
| `task_id` | VARCHAR(64) | NOT NULL | |
| `query_user_id` | VARCHAR(64) | NOT NULL | 调用详情 API 时的 userId |
| `unique_id` | INTEGER | NULL | |
| `content` | TEXT | | |
| `executor_id` | VARCHAR(64) | | |
| `creator_id` | VARCHAR(64) | | |
| `scenario_field_config_id` | VARCHAR(64) | | |
| `taskflow_status_id` | VARCHAR(64) | | |
| `task_list_id` | VARCHAR(64) | | |
| `task_stage_id` | VARCHAR(64) | | |
| `due_date` | DATETIME | NULL | |
| `start_date` | DATETIME | NULL | |
| `is_done` | BOOLEAN | | |
| `is_archived` | BOOLEAN | | |
| `priority` | INTEGER | | |
| `progress` | INTEGER | | |
| `note` | TEXT | | |
| `visible` | VARCHAR(32) | | |
| `tag_ids` | JSON | NULL | |
| `involve_members` | JSON | NULL | |
| `ancestor_ids` | JSON | NULL | |
| `labels` | JSON | NULL | |
| `custom_fields_json` | JSON | NULL | 全部 customFields 原始结构 |

### 6.2 拆列字段

| 列名 | 类型 | 来源 cfId | 含义 |
|------|------|-----------|------|
| `vehicle_model` | VARCHAR(128) | `659369d3...` | **车型** |
| `carrier_type` | VARCHAR(32) | `637c2e2f...` | **载具配置** |
| `occurrence_frequency` | VARCHAR(32) | `62c51d82...` | **复现概率** |
| `software_version` | VARCHAR(32) | `6645bd4d...` | **JZTOTAL包版本** |

### 6.3 兜底

| 列名 | 类型 | 说明 |
|------|------|------|
| `raw_json` | TEXT | NULL | 完整钉钉响应 JSON |

**唯一约束**：`UNIQUE (task_id, query_user_id)`

---

## 7. 与主项目隔离

| | 主项目 | onsite_problem |
|---|---|---|
| 数据库 | `benti_management` | `onsite_problem` |
| projectId | `647854bc4a622b2e3199fa5a` | `616e6868a46ec51df166f4cd` |
| A 表 | `project_tasks` | `onsite_problem_tasks` |
| B 表 | `project_task_details` | `onsite_problem_details` |
| customField | 固定模板 | 动态模板（基础+扩展） |

---

## 8. 修订记录

| 日期 | 说明 |
|------|------|
| 2026-07-22 | 初稿：customField 16个全部确认，A/B 表设计 |
