# KB 知识库表设计文档

> 参考 onsite_problem 的 A/B 表模式，重构 kb_storage 库为三表架构。

## 设计目标

1. **目录树持久化** — 遍历结果可查可复用，不每次调 API 回溯
2. **断点续传** — 同步中断后可精准恢复，不重拉已完成的文档
3. **增量更新** — 基于 `remote_modified_at` 只拉变更文档
4. **状态可追踪** — 每步有明确的状态字段，方便排查和统计

---

## 表结构

### kb_nodes（A 表）— 目录树快照

存储所有知识库的目录结构（FOLDER + FILE），一次遍历后永久可查。

| 列名 | 类型 | 说明 |
|---|---|---|
| id | INT PK AUTO_INCREMENT | 自增主键 |
| node_id | VARCHAR(128) NOT NULL | 钉钉节点 ID，唯一索引 |
| workspace_id | VARCHAR(128) NOT NULL | 所属知识库 ID，索引 |
| parent_id | VARCHAR(128) DEFAULT '' | 父节点 ID，根节点为空，索引 |
| name | VARCHAR(512) NOT NULL | 节点名称（文件名/文件夹名） |
| node_type | VARCHAR(16) NOT NULL | FOLDER / FILE |
| category | VARCHAR(16) DEFAULT '' | ALIDOC / WORKBOOK / OTHER（仅 FILE 有效） |
| has_children | BOOLEAN DEFAULT FALSE | 是否还有子节点 |
| depth | INT DEFAULT 0 | 目录深度，根 = 0 |
| breadcrumb | VARCHAR(1024) DEFAULT '' | 完整路径，如 `本体开发部 / 导航组 / Roadmap` |
| remote_modified_at | DATETIME NULL | 钉钉最后修改时间，用于增量同步判断 |
| sync_status | VARCHAR(16) DEFAULT 'pending' | pending / synced / failed |
| sync_error | VARCHAR(500) DEFAULT '' | 同步失败原因 |
| synced_at | DATETIME NOT NULL | 最后同步时间 |
| created_at | DATETIME NOT NULL | 创建时间 |
| updated_at | DATETIME NOT NULL | 更新时间 |

- **唯一约束**: `(workspace_id, node_id)`
- **索引**: `parent_id`, `sync_status`

### kb_documents（B 表）— 文档正文

仅存储 FILE 节点的正文内容，与 kb_nodes 通过 node_id 一一对应。

| 列名 | 类型 | 说明 |
|---|---|---|
| id | INT PK AUTO_INCREMENT | 自增主键 |
| node_id | VARCHAR(128) NOT NULL | 关联 kb_nodes.node_id，唯一索引 |
| workspace_id | VARCHAR(128) NOT NULL | 冗余字段，方便按 workspace 查，索引 |
| title | VARCHAR(512) NOT NULL | 冗余字段，方便检索 |
| content | MEDIUMTEXT | 正文 Markdown |
| raw_json | MEDIUMTEXT | get_document_blocks API 原始返回 |
| error_code | VARCHAR(16) NULL | 解析出的错误码，索引（可为空） |
| fetch_status | VARCHAR(16) DEFAULT 'pending' | pending / success / failed |
| fail_reason | VARCHAR(500) DEFAULT '' | 内容拉取失败原因 |
| synced_at | DATETIME NOT NULL | 最后同步时间 |
| created_at | DATETIME NOT NULL | 创建时间 |
| updated_at | DATETIME NOT NULL | 更新时间 |

- **唯一约束**: `node_id`
- **索引**: `fetch_status`, `error_code`

### kb_chunks（C 表）— 检索分块

不动，保持现有结构。`doc_id` 对应 `kb_documents.node_id`。

| 列名 | 类型 | 说明 |
|---|---|---|
| id | INT PK AUTO_INCREMENT | 自增主键 |
| doc_id | VARCHAR(128) NOT NULL | 关联 kb_documents.node_id，索引 |
| chunk_index | INT NOT NULL | 分块序号 |
| content | TEXT NOT NULL | 分块内容 |
| token_count | INT DEFAULT 0 | Token 数量 |
| created_at | DATETIME NOT NULL | 创建时间 |

- **复合索引**: `(doc_id, chunk_index)`

---

## 表关系

```
kb_nodes (A)                kb_documents (B)            kb_chunks (C)
─────────────               ────────────────            ────────────
node_id ────────── 1:1 ──→ node_id ────── 1:N ──→ doc_id
workspace_id                workspace_id                chunk_index
parent_id ─┐                title                       content
name        │ 自引用          content                     token_count
node_type   │                raw_json
depth       │                error_code
breadcrumb  │                fetch_status
sync_status │                fail_reason
            └── parent_id
```

---

## 同步流程

### Phase 1: 遍历目录树

```
写入 kb_nodes
    │
    ├─ list_workspaces() → 获取所有知识库 rootNodeId
    │
    └─ 对每个 workspace:
        │
        └─ _walk_flat(workspace_id, root_node_id, depth=0, breadcrumb="")
            │
            ├─ 写当前节点到 kb_nodes (sync_status='synced')
            │
            ├─ list_nodes(parent_id) → 获取子节点
            │
            └─ 对每个子节点:
                ├─ FOLDER → 递归 _walk_flat(..., depth+1, breadcrumb + "/" + name)
                └─ FILE   → 写 kb_nodes，标记待下载
```

### Phase 2: 下载文档内容

```
查 kb_nodes WHERE node_type='FILE' AND sync_status='synced'
LEFT JOIN kb_documents ON kb_nodes.node_id = kb_documents.node_id
WHERE kb_documents.node_id IS NULL        ← 未下载
   OR kb_documents.fetch_status='failed'  ← 上次失败
   OR kb_nodes.remote_modified_at > kb_documents.updated_at  ← 远程有更新

对每条待下载的 node:
    │
    ├─ get_document_blocks(node_id) → parse → Markdown
    │
    ├─ 成功 → 写 kb_documents (fetch_status='success')
    │
    └─ 失败 → 写 kb_documents (fetch_status='failed', fail_reason='...')
```

### Phase 3: 分块 + 向量化（不变）

```
查 kb_documents WHERE fetch_status='success' AND content != ''
选出 content 有变化的 docs → rechunk → embed
```

---

## 同步模式

### 增量同步（incremental）
```
foreach workspace:
    foreach folder in kb_nodes (depth=0):
        compare kb_nodes.modified_at with remote
        if remote changed → re-walk this subtree
        else → skip
```

### 失败重试
```
SELECT node_id FROM kb_documents WHERE fetch_status = 'failed'
→ 只重拉这些文档
```

### 断点续传
```
中断后重启:
    SELECT COUNT(*) FROM kb_nodes WHERE sync_status = 'pending'
    → 从未遍历完的目录继续
    
    SELECT COUNT(*) FROM kb_documents WHERE fetch_status = 'pending'
    → 从未下载完的文档继续
```

---

## 迁移路径

现有 `kb_documents` 表数据迁移到新表结构：

1. 从 `kb_documents` 中提取 `parent_id`、`node_id`，写入 `kb_nodes`（node_type='FILE'）
2. FOLDER 节点在旧表中不存在，需首次全量遍历补全
3. 内容字段保留在 `kb_documents`
4. `kb_chunks` 不动，但 `doc_id` 需指向 `kb_nodes.node_id`（本身就一致）

---

## 当前状态

| 表 | 状态 |
|---|---|
| kb_nodes | ❌ 待创建 |
| kb_documents | ⚠️ 存在但缺少 category / remote_modified_at / error_code / fetch_status 字段 |
| kb_chunks | ✅ 正常 |
| api_call_logs | ✅ 已建立，限额 2,000,000 |
