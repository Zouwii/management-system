# tb_tool_bt 数据库设计说明

本文描述 **钉钉项目任务同步** 相关的持久化设计，与 `tb_tool_backend`（Teambition + SQLite + Redis）**相互独立**。Redis 仅作接口缓存与辅助，**不作为业务真相源**；真相源为本库中的表。

---

## 1. 设计目标

| 业务 | 数据来源 | 持久化目标 |
|------|-----------|------------|
| **A：项目任务列表** | `POST/GET …/projectIds/{projectId}/tasks`（列表，可翻页） | 全量/定期同步，筛「软件开发」等规则后 **upsert 主表** |
| **B：任务明细与工时** | `…/users/{userId}/tasks?taskId=…`（单条详情） | 对选定 `task_id` **逐条查询**后写入 **明细/快照表** |

代码侧领域模型（解析用，非 DDL）：

- 列表行：`backend/models/dingtalk_project_task.py` → `DingTalkProjectTaskRow`
- 明细行：`backend/models/dingtalk_task_detail.py` → `DingTalkTaskDetailRow`

---

## 2. 表一览

| 表名 | 别名 | 说明 |
|------|------|------|
| `project_tasks` | **A 表** | 项目下任务列表快照（浅字段，`customfields` 常无 value） |
| `project_task_details` | **B 表** | 单任务详情快照（含 `customFields` 全量或抽取的工时等） |
| `sync_runs` | 可选 | 同步批次元数据（对账、排障） |

---

## 3. 表 `project_tasks`（A）

### 3.1 用途

- 存储列表接口返回、并经业务规则过滤后的任务（例如 `scenario_field_config_id` = 软件开发）。
- 列表字段以 **稳定、可筛选** 为主；**不依赖**本表存完整工时（工时在 B 表或解析列）。

### 3.2 建议列

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | BIGINT / INTEGER | PK, 自增 | 内部主键 |
| `project_id` | VARCHAR(64) | NOT NULL | 项目 ID |
| `task_id` | VARCHAR(64) | NOT NULL | 钉钉任务 ID |
| `content` | TEXT | | 标题 |
| `scenario_field_config_id` | VARCHAR(64) | | 任务类型/场景（用于筛「软件开发」） |
| `stage_id` | VARCHAR(64) | | 列表接口常见 `stageId`（若仅有 `taskStageId` 可映射） |
| `taskflow_status_id` | VARCHAR(64) | | 工作流状态 |
| `executor_id` | VARCHAR(64) | | 执行者 |
| `creator_id` | VARCHAR(64) | | 创建者 |
| `due_date` | TIMESTAMPTZ / DATETIME | NULL | 截止 |
| `ding_created` | TIMESTAMPTZ | NULL | 钉钉 `created` |
| `ding_updated` | TIMESTAMPTZ | NULL | 钉钉 `updated` |
| `note` | TEXT | | 备注 |
| `priority` | INT | DEFAULT 0 | |
| `progress` | INT | DEFAULT 0 | |
| `visible` | VARCHAR(32) | | 可见范围 |
| `is_archived` | BOOLEAN | DEFAULT false | |
| `is_deleted` | BOOLEAN | DEFAULT false | |
| `is_done` | BOOLEAN | DEFAULT false | |
| `ancestor_ids` | JSON / TEXT | NULL | `ancestorIds` 数组 |
| `involve_members` | JSON / TEXT | NULL | `involveMembers` |
| `tag_ids` | JSON / TEXT | NULL | `tagIds` |
| `labels` | JSON / TEXT | NULL | `labels` |
| `customfield_ids` | JSON / TEXT | NULL | 列表项仅有 id 时，存 id 数组即可 |
| `list_synced_at` | TIMESTAMPTZ | NULL | 本条由列表同步写入/更新的时间 |

**唯一约束**：`UNIQUE (project_id, task_id)`

**索引建议**：

- `(project_id, scenario_field_config_id)` — 按项目 + 类型筛选
- `(executor_id)` — 按执行者统计（按需）
- `(ding_updated)` — 增量同步（若后续按更新时间拉取）

### 3.3 同步策略（逻辑）

- 拉列表（可多页 `nextToken`）→ 应用业务过滤 → **INSERT … ON CONFLICT (project_id, task_id) DO UPDATE**（或等价 upsert）。
- 列表中已删除任务：若接口提供 `isDeleted`，可软删或物理删策略由产品定。

---

## 4. 表 `project_task_details`（B）

### 4.1 用途

- 存储 **单任务详情接口**（`POST /api/bt/query_task_details`）返回：`customFields` 含 `type`、`value`，用于**工时**及后续扩展字段。
- 与 A 表 **一对多（历史模式）或一对一（最新覆盖模式）**，见 4.3。

### 4.2 建议列

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | BIGINT | PK, 自增 | |
| `project_id` | VARCHAR(64) | NOT NULL | 冗余，便于按项目查询 |
| `task_id` | VARCHAR(64) | NOT NULL | |
| `query_user_id` | VARCHAR(64) | NOT NULL | 调用详情 API 时的 `userId`（路径参数） |
| `work_hour_field_id` | VARCHAR(64) | NULL | 本次解析使用的自定义字段 ID（如有效工时） |
| `work_hour` | DECIMAL(12,4) / DOUBLE | NULL | 解析后的标量工时（便于汇总） |
| `custom_fields_json` | JSON / TEXT | NULL | `customFields` 整段或压缩结构 |
| `raw_json` | TEXT | NULL | 可选：完整钉钉响应片段，排障 |
| `fetched_at` | TIMESTAMPTZ | NOT NULL | 本次拉取时间 |

可选扩展（与 `DingTalkTaskDetailRow` 对齐）：`parent_task_id`、`task_list_id`、`task_stage_id`、`unique_id`。

### 4.3 两种业务模式（择一）

**模式 1：仅保留最新（推荐上手简单）**

- 唯一约束：`UNIQUE (task_id, query_user_id)`
- 每次 for 循环拉到新数据 → **覆盖更新** 同行，`fetched_at` 更新。

**模式 2：保留历史**

- 不设上述唯一键；每次拉取 **插入新行**。
- 查询「当前工时」：`ORDER BY fetched_at DESC LIMIT 1` per `(task_id, query_user_id)`。

### 4.4 索引建议

- `(task_id, query_user_id, fetched_at DESC)` — 取最新快照
- `(project_id, fetched_at)` — 按项目清理或统计

---

## 5. 表 `sync_runs`（可选）

| 列名 | 类型 | 说明 |
|------|------|------|
| `id` | BIGSERIAL / INTEGER PK | |
| `sync_type` | VARCHAR(32) | `list` / `detail_batch` |
| `project_id` | VARCHAR(64) | 可选 |
| `started_at` / `finished_at` | TIMESTAMPTZ | |
| `row_count` | INT | 写入/更新行数 |
| `error_message` | TEXT | 失败记录 |

用于排查「哪次全量列表同步写了多少条」「明细批次是否半路失败」。

---

## 6. 表关系（逻辑）

```text
project_tasks (A)
    1 ────────── *    project_task_details (B)   [历史模式：多条快照]
    或
    1 ────────── 1    project_task_details (B)   [最新覆盖：task_id + query_user_id 唯一]
```

- **外键**：可将 B.`(project_id, task_id)` 逻辑关联 A（若使用仅 `task_id` 全局唯一，可只关联 `task_id`）。是否建物理外键视 DB 与删改策略而定。
- **不强求**：B 可在 A 尚未同步时单独写入（例如仅对已知 `task_id` 拉明细），但建议业务上 **task_id 与 project_id 与 A 一致**，便于联表报表。

---

## 7. 与 Redis 的分工（非表结构，供部署对齐）

| 组件 | 职责 |
|------|------|
| **本库** | 存储 A、B 及可选 `sync_runs` |
| **Redis（可选）** | 短时缓存列表/单任务详情响应，降低钉钉 QPS；**不以 Redis 为准做结账** |

缓存 key 示例（实现时自定前缀与 TTL）：

- 列表：`bt:list:{project_id}:{query_hash}`
- 详情：`bt:task:{query_user_id}:{task_id}`

---

## 8. 技术栈与演进

- **开发期**：SQLite / 单文件库即可（注意并发写与 WAL）。
- **生产**：PostgreSQL / MySQL 等，JSON 列类型与 `TIMESTAMPTZ` 按厂商调整。
- **迁移**：建议使用迁移工具（如 Alembic）管理 DDL；本文档为逻辑设计，具体类型以目标库为准。

---

## 9. 修订记录

| 日期 | 说明 |
|------|------|
| 2026-03-28 | 初稿：A/B 表 + 可选 sync_runs + Redis 分工；项目名 tb_tool_bt，缓存前缀 `bt:` |
