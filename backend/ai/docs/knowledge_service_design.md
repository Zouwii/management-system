# 知识库文档查阅与下载服务 设计文档

## 1. 目标与范围

实现钉钉知识库的文档查阅和下载服务，作为 RAG 系统的 **Phase 1（数据源验证）+ Phase 2（文档同步与索引）** 的第一个里程碑。

### 1.1 本期目标

- 通过钉钉 API 浏览知识库空间和文档目录
- 下载文档正文内容
- 解析 HTML/富文本 → Markdown
- 持久化到 SQLite

### 1.2 非本期目标

- 文档切片（留到 chunker 阶段）
- 向量化 / 全文检索
- 定时同步（先做手动触发）

---

## 2. 钉钉知识库 API 调研

API 调用统一通过 `dingtalk_client.py` 的 `get_valid_access_token()` 获取 token，请求头携带 `x-acs-dingtalk-access-token`。

### 2.1 已验证：知识库列表

```
GET https://api.dingtalk.com/v1.0/doc/workspaces
Headers: x-acs-dingtalk-access-token: <token>
Params:  unionId=<被查询用户的unionId>
         includeRecent=true|false（可选）
```

**返回字段：** name, workspaceId, owner, role, isDeleted, createTime, recentList

> ⚠️ 该接口已于 2023 年 7 月标记为"不推荐"，但目前仍可使用。后续若有问题，替代接口参考 [v2.0 wiki](https://open.dingtalk.com/document/isvapp/query-the-directory-structure-in-the-knowledge-base)。

### 2.2 待验证：知识库节点列表

推测接口（基于钉钉开放平台文档目录的 URL slug `get-node-list`）：

```
GET https://api.dingtalk.com/v2.0/wiki/nodes
Headers: x-acs-dingtalk-access-token: <token>
Params:  workspaceId=<知识库ID>
         nodeId=<父节点ID，不传则从根目录开始>
```

**优先级一：** 实际调用并确认 HTTP 方法、参数名、返回结构。

### 2.3 待验证：文档正文获取

推测接口（基于 URL slug `get-knowledge-base-acquisition-node`）：

```
GET https://api.dingtalk.com/v2.0/wiki/nodes/{nodeId}
Headers: x-acs-dingtalk-access-token: <token>
```

**优先级一：** 实际调用并确认返回结构中是否包含 HTML/富文本正文。

如果该接口不返回正文，需进一步寻找文档内容导出接口（参考 `knowledge-base-download-file`）。

### 2.4 待验证：文件下载接口

知识库中的附件（PDF、图片等），通过 drive spaces 接口下载：

```
GET https://api.dingtalk.com/v1.0/drive/spaces/{spaceId}/files/{fileId}/downloadInfos
Headers: x-acs-dingtalk-access-token: <token>
```

需要 `Drive.DownloadInfo.Read` 权限。

---

## 3. 后端架构

### 3.1 模块结构

```
backend/ai/knowledge/
├── __init__.py      # register(bp, ok, fail)
├── routes.py        # HTTP 端点：workspaces, nodes, documents, sync
├── service.py       # 钉钉知识库 API 调用（DingTalkApiClient）
├── parser.py        # 文档清洗：HTML/富文本 → Markdown
└── models.py        # SQLAlchemy ORM 模型
```

### 3.2 注册方式

遵循项目现有模式：

```
api.py: api_bp (Blueprint, prefix="/api/bt")
    → route_registry/__init__.py: register_all_routes()
        → ai/__init__.py: register_all_routes()
            → ai/knowledge/__init__.py: register(bp, ok, fail)
```

### 3.3 依赖关系

```
routes.py
  ├── service.py       → 钉钉 API 调用
  │     └── dingtalk_client.py   → get_valid_access_token()
  ├── parser.py        → 文档格式转换
  │     └── bleach + markdownify (或纯正则)
  └── models.py        → KbDocument, KbChunk
        └── db/engine.py → SessionLocal
```

---

## 4. API 端点设计

### 4.1 获取知识库列表

```
GET /api/bt/ai/knowledge/workspaces

→ 调用 DingTalk API 获取用户有权限的知识库列表
→ 同时回写本地 DB（更新 kb_documents 中 workspace 记录）

Response 200:
{
  "code": 200, "error": "",
  "data": {
    "workspaces": [
      {
        "workspaceId": "xxx",
        "name": "导航组知识库",
        "role": "EDITOR",
        "nodeCount": 42,
        "lastSyncedAt": "2026-05-26T10:00:00Z"
      }
    ]
  }
}
```

### 4.2 获取文档/目录树

```
GET /api/bt/ai/knowledge/workspaces/<workspace_id>/nodes?node_id=<parent_node_id>

- node_id 可选，不传则列出根目录下的节点
- 每个 node 返回 type: "folder" | "document"
- 如果有本地 DB 缓存，直接返回（带 lastSyncedAt 标记）

Response 200:
{
  "code": 200, "error": "",
  "data": {
    "workspaceId": "xxx",
    "parentId": "root",
    "nodes": [
      { "nodeId": "yyy", "title": "需求文档规范", "type": "document", "cached": true },
      { "nodeId": "zzz", "title": "操作手册", "type": "folder", "childCount": 12 }
    ]
  }
}
```

### 4.3 获取文档内容

```
GET /api/bt/ai/knowledge/documents/<node_id>

流程:
  1. 查本地 kb_documents 表
  2. 命中 → 直接返回
  3. 未命中 → 调钉钉 API 获取正文 → parser.html_to_markdown()
     → 存入 kb_documents → 返回

Response 200:
{
  "code": 200, "error": "",
  "data": {
    "nodeId": "yyy",
    "title": "需求文档规范",
    "workspaceId": "xxx",
    "content": "# 需求文档规范\n\n## 1. 概述\n...",
    "format": "markdown",
    "source": "cache" | "dingtalk_api",
    "syncedAt": "2026-05-26T10:05:00Z"
  }
}
```

### 4.4 手动同步

```
POST /api/bt/ai/knowledge/sync
Body: { "workspace_id": "xxx", "full_sync": true }

流程:
  1. 遍历知识库节点树（广度优先）
  2. 对每个 document 类型节点，下载正文 → 解析 → 写入 DB
  3. folder 类型节点继续递归
  4. 记录同步日志

Response 200:
{
  "code": 200, "error": "",
  "data": {
    "workspaceId": "xxx",
    "syncedCount": 35,
    "failedCount": 2,
    "errors": [
      { "nodeId": "aaa", "title": "旧版文档", "error": "API 返回 404" }
    ],
    "startedAt": "...",
    "finishedAt": "..."
  }
}
```

---

## 5. 数据模型

### 5.1 kb_documents（文档主表）

```sql
CREATE TABLE IF NOT EXISTS kb_documents (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id          TEXT UNIQUE NOT NULL,      -- 钉钉节点 ID
    workspace_id    TEXT NOT NULL,             -- 所属知识库 ID
    title           TEXT NOT NULL,             -- 文档标题
    node_type       TEXT NOT NULL DEFAULT 'document',  -- folder | document
    parent_id       TEXT DEFAULT '',           -- 父节点 ID
    content         TEXT DEFAULT '',           -- 清洗后的 Markdown 正文
    raw_json        TEXT DEFAULT '',           -- 钉钉 API 原始返回 JSON
    synced_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_kb_docs_workspace ON kb_documents(workspace_id);
CREATE INDEX IF NOT EXISTS idx_kb_docs_parent ON kb_documents(parent_id);
```

### 5.2 kb_chunks（文档分片表）

```sql
CREATE TABLE IF NOT EXISTS kb_chunks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id          TEXT NOT NULL REFERENCES kb_documents(doc_id),
    chunk_index     INTEGER NOT NULL,          -- 分片序号（从 0 开始）
    content         TEXT NOT NULL,             -- 分片文本
    token_count     INTEGER DEFAULT 0,         -- token 估算数
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_kb_chunks_doc ON kb_chunks(doc_id, chunk_index);
```

### 5.3 FTS5 全文索引（预留）

```sql
-- 本期先建表，数据在 chunker 阶段填充
CREATE VIRTUAL TABLE IF NOT EXISTS kb_chunks_fts USING fts5(
    content, content=kb_chunks, content_rowid=id
);
```

### 5.4 SQLite ORM 模型（Python）

```python
from sqlalchemy import (
    Integer, String, Text, DateTime, UniqueConstraint, Index,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from datetime import datetime, timezone


class KbDocument(Base):
    __tablename__ = "kb_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doc_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    node_type: Mapped[str] = mapped_column(String(16), default="document")
    parent_id: Mapped[str] = mapped_column(String(128), default="")
    content: Mapped[str] = mapped_column(Text, default="")
    raw_json: Mapped[str] = mapped_column(Text, default="")
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                                                 onupdate=lambda: datetime.now(timezone.utc))


class KbChunk(Base):
    __tablename__ = "kb_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doc_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_kb_chunks_doc", "doc_id", "chunk_index"),
    )
```

---

## 6. 文档解析器（parser.py）

### 6.1 输入

钉钉 API 返回的文档正文，可能是以下格式之一：
- **富文本/JSON 块结构**（钉钉文档 block 格式）
- **HTML**（知识库页面渲染用）
- **纯文本**

### 6.2 输出

清洗后的 Markdown 文本。

### 6.3 处理流水线

```
原始内容
  → [1] 识别格式（JSON block 结构 / HTML / 纯文本）
  → [2] 如果是 JSON block 结构 → 递归解析 block tree → Markdown
  → [3] 如果是 HTML → markdownify 或 bleach+手动转换 → Markdown
  → [4] 如果是纯文本 → 直接透传
  → [5] 清理多余空行，统一换行符
```

### 6.4 各格式处理策略

| 原始格式 | 处理方式 |
|---------|---------|
| 标题（H1-H6） | → `#` ~ `######` |
| 加粗/斜体 | → `**text**` / `*text*` |
| 列表（ol/ul） | → markdown 列表 |
| 链接 | → `[text](url)` |
| 代码块 | → \`\`\` 包裹 |
| 表格 | → markdown table |
| 图片 | → 保留 alt text: `![alt](url)` |
| 附件/文件 | → `[文件名](下载链接)` |
| 分割线 | → `---` |

### 6.5 错误降级

- 如果解析失败，返回原始文本并标记 `parse_status = "raw"`
- 不阻断流程，允许后续手动处理

---

## 7. 钉钉 API 客户端（service.py）

### 7.1 核心方法

```python
class DingTalkKnowledgeClient:
    def __init__(self, access_token: str):
        self.token = access_token
        self.base_url = "https://api.dingtalk.com"
        self._session = requests.Session()
        self._session.headers.update({
            "x-acs-dingtalk-access-token": access_token,
            "Content-Type": "application/json",
        })

    def list_workspaces(self, union_id: str, include_recent: bool = False) -> list[dict]:
        """获取用户有权限的知识库列表"""

    def list_nodes(self, workspace_id: str, node_id: str = "") -> list[dict]:
        """获取知识库下的文档/目录节点"""

    def get_node_detail(self, node_id: str) -> dict:
        """获取单个节点的详细信息（含正文）"""
```

### 7.2 错误处理

- 统一捕获 `requests.RequestException`，转为结构化错误返回
- API 返回非 200 → 记录完整响应用于排障
- 限流（429）→ 重试一次（等 3 秒 + 指数退避）
- Token 过期 → 重新获取 token 后重试一次

### 7.3 日志

所有 API 调用记入 `runtime/logs/ai_debug.log`：
```json
{"ts": 1234567890, "phase": "kb_api", "endpoint": "/v1.0/doc/workspaces",
 "status": 200, "latency_ms": 345}
```

---

## 8. 数据库初始化

### 8.1 表创建

在 `db/engine.py` 的 `init_database()` 中新增：
- `kb_documents` 表
- `kb_chunks` 表
- `kb_chunks_fts` 虚拟表（FTS5）

### 8.2 非侵入式

不修改 `Base.metadata` 的全局注册方式，而是在 knowledge module 的 models.py 中使用独立的 init 函数，由 `init_database()` 显式调用。

---

## 9. 需要新建/修改的文件

### 新建

| 文件 | 说明 |
|------|------|
| `backend/ai/docs/knowledge_service_design.md` | 本文档 |
| `backend/ai/knowledge/__init__.py` | 模块注册 |
| `backend/ai/knowledge/routes.py` | 4 个 API 端点 |
| `backend/ai/knowledge/service.py` | DingTalkKnowledgeClient |
| `backend/ai/knowledge/parser.py` | 文档格式转换 |
| `backend/ai/knowledge/models.py` | ORM 模型 |

### 修改

| 文件 | 改动 |
|------|------|
| `backend/ai/__init__.py` | 增加 `_register_knowledge` 调用 |
| `backend/db/engine.py` | `init_database()` 中创建 kb 相关表 |

---

## 10. 验证清单

- [ ] `GET /ai/knowledge/workspaces` 返回知识库列表
- [ ] `GET /ai/knowledge/workspaces/<id>/nodes` 返回文档目录树
- [ ] `GET /ai/knowledge/documents/<node_id>` 返回 Markdown 正文
- [ ] 检查 `backend/data/tb_tool_bt.db` 中 `kb_documents` 表有数据
- [ ] `POST /ai/knowledge/sync` 手动触发同步，返回同步统计
