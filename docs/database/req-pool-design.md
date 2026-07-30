# req_pool 数据库设计说明

本文描述 **需求池项目**（Teambition projectId: `631710f1ac04e183d048d326`）的持久化设计，沿用 `onsite_problem` 的 A/B 表模式。

---

## 1. customField 定义

基于任务 `6a16a11056e711103b1b6be9` 的 API 返回数据及全量 3000+ 条采样定义。

### 1.1 B 表拆列字段（10 个）

| cfId | type | 列名 | 业务含义 | 示例值 |
|------|------|------|----------|--------|
| `631716de7f7344003f3ece70` | dropDown | `req_source` | **需求来源** | `产品需求` |
| `631715ae6b9968003f9d8663` | text | `title` | **标题** | `出厂流程优化九期合入主干（3.2605）` |
| `636243182a3467003f8421fd` | dropDown | `branch` | **主干/分支** | `主干功能` |
| `650d01985926ce31ac8567ec` | dropDown | `release_version` | **发布版本** | `3.2605` |
| `63ff1addd450590017455ec0` | text | `package_version` | **子包版本** | `见测试报告` |
| `634e8177cc2f290040ad67b5` | lookup2 | `prd_doc` | **PRD文档** | `出厂标定专项26Q1需求` |
| `634e81ba28f0e20040b97303` | lookup2 | `dev_doc` | **研发文档** | `出厂工具链【九期】软件方案` |
| `634e8825fddc0e003feca663` | lookup2 | `test_case` | **测试用例** | `出厂工具链【九期】测试用例` |
| `634e81d65e75170040a27116` | lookup2 | `test_report` | **测试报告** | `出厂工具链【九期】测试报告` |
| `65f2ca0eae786a9021262156` | lookup | `biz_owner` | **业务负责人** | `裘鹏程` |

### 1.2 其他字段（JSON 兜底，不拆列）

全量 3000+ 条中共出现 49 个不同的 customField。除上述 10 个拆列字段外，其余 39 个字段仅存于 `custom_fields_json`。其中较常见但暂未拆列的：

| cfId | type | 频次 | 示例值 |
|------|------|------|--------|
| `64fee881eec914e302e0375e` | number | 779 | `80` |
| `63171c14a01d84003f1a50c7` | date | 250 | `2023-03-31T03:43:00.000Z` |
| `5ebdfef27405369835777f41` | lookup | 234 | `1` |
| `5ebdfef2fb3ff01529e26bd2` | lookup | 234 | `「绿」 状态正常` |
| `5ee884449bb7dfaeadbf515c` | date | 234 | `2022-08-01T05:42:03.322Z` |
| `634e82063b9f1700408cb519` | lookup2 | 136 | `无【研发】` |
| `631838b686327c003fee72b5` | date | 77 | `2022-12-16T12:15:00.000Z` |
| `634e7897cfbd6d0040696020` | text | 61 | `jz_control_od 0.2.0-od33` |
| `6419286c4a622b2e317cd23c` | lookup | 49 | `2023-02发布计划（测试中）` |

> 说明：需求池包含多套模板，不同模板的任务有不同的字段组合。A 表 `raw_json` 保留了完整的 DingTalk 返回，后续可随时从中解析新字段追加到 B 表。

---

## 2. 设计目标

| 业务 | 数据来源 | 持久化目标 |
|------|-----------|------------|
| **A：任务列表** | DingTalk 项目 API | 定期同步，全量 upsert |
| **B：任务明细** | TB Open API via 钉钉代理 `open.teambition.com/api/v3` | 逐条拉取详情 + 评论 + 附件 |

---

## 3. 表一览

| 表名 | 别名 | 说明 |
|------|------|------|
| `req_pool_tasks` | **A 表** | 列表快照（顶层字段 + raw_json） |
| `req_pool_details` | **B 表** | 明细快照（解析关键 customField + raw_json 兜底） |

**数据库**：独立库 `req_pool`

---

## 4. 项目配置

| 配置项 | 值 |
|--------|-----|
| projectId | `631710f1ac04e183d048d326` |
| 项目名 | 需求池 |

---

## 5. 表 `req_pool_tasks`（A 表）

### 5.1 列定义

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INTEGER | PK, 自增 | |
| `project_id` | VARCHAR(64) | NOT NULL | `631710f1ac04e183d048d326` |
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

## 6. 表 `req_pool_details`（B 表）

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

| 列名 | 类型 | 来源 cfId | 业务含义 |
|------|------|-----------|----------|
| `req_source` | VARCHAR(64) | `631716de...` | **需求来源** |
| `title` | TEXT | `631715ae...` | **标题** |
| `branch` | VARCHAR(64) | `63624318...` | **主干/分支** |
| `release_version` | VARCHAR(64) | `650d0198...` | **发布版本** |
| `package_version` | VARCHAR(64) | `63ff1add...` | **子包版本** |
| `prd_doc` | VARCHAR(512) | `634e8177...` | **PRD文档** |
| `dev_doc` | VARCHAR(512) | `634e81ba...` | **研发文档** |
| `test_case` | VARCHAR(512) | `634e8825...` | **测试用例** |
| `test_report` | VARCHAR(512) | `634e81d6...` | **测试报告** |
| `biz_owner` | VARCHAR(64) | `65f2ca0e...` | **业务负责人** |

### 6.3 评论流 + 附件流

| 列名 | 类型 | 说明 |
|------|------|------|
| `comments_json` | MEDIUMTEXT | NULL | 评论流 JSON，按时间正序 |
| `attachments_json` | MEDIUMTEXT | NULL | 附件流 JSON，含 metadata |

结构同 `onsite_problem_details` 中的 `comments_json` / `attachments_json`。

### 6.4 兜底

| 列名 | 类型 | 说明 |
|------|------|------|
| `raw_json` | TEXT | NULL | 完整 TB Open API 响应 JSON |

**唯一约束**：`UNIQUE (task_id, query_user_id)`

---

## 7. 项目隔离

| | 主项目 | onsite_problem | req_pool |
|---|---|---|---|
| 数据库 | `benti_management` | `onsite_problem` | `req_pool` |
| projectId | `647854bc4a622b2e3199fa5a` | `616e6868a46ec51df166f4cd` | `631710f1ac04e183d048d326` |
| A 表 | `project_tasks` | `onsite_problem_tasks` | `req_pool_tasks` |
| B 表 | `project_task_details` | `onsite_problem_details` | `req_pool_details` |
| customField | 固定模板 | 固定模板 | 多模板混合 |

---

## 8. 同步流程

```
A 表同步
  └─ DingTalk 项目 API → req_pool_tasks（断点续拉）

B 表同步（TB Open API via proxy）
  ├─ 从 A 表读取 task_id 列表
  ├─ 每条 task_id：
  │   ├─ GET task/query            → 任务详情 + customField 解析
  │   ├─ GET task/{id}/activity/list → 评论流（翻页到底）
  │   └─ POST file/query/by-resource-ids → 附件元数据
  └─ upsert req_pool_details（含 comments_json + attachments_json）
```

**认证**：复用 onsite 的 TB Open API 代理，凭据共享。

**附件策略**：只存元数据（resource_id, file_name, file_size, mime_type），不存 download_url。

---

## 9. 修订记录

| 日期 | 说明 |
|------|------|
| 2026-07-27 | 初稿：customField 10 个拆列字段定义，A/B 表设计 |
