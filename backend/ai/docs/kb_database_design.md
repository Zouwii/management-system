# 知识库数据库设计

> 最后更新: 2026-05-27

## 1. 数据库分布

| 数据库 | 连接 | 内容 |
|--------|------|------|
| **MySQL `tb_management`** | `DATABASE_URI`，项目主库 | 业务数据 + 知识库文档正文 + 切片文本 + 全文索引 |
| **PostgreSQL `kb_vectors`** | `PGVECTOR_DATABASE_URI` | 切片 Embedding 向量 + HNSW 索引 |
| MySQL `perf_quarter_result` | `PERF_DATABASE_URI` | 绩效数据（独立库） |

环境切换：`.env` 中 `TB_TOOL_BT_USE_MYSQL=1` 走 MySQL，否则走本地 SQLite。pgvector 始终用 PostgreSQL。

---

## 2. kb_documents — 文档主表

### 表结构

```sql
CREATE TABLE kb_documents (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    doc_id          VARCHAR(128) NOT NULL UNIQUE,   -- 钉钉节点 ID
    workspace_id    VARCHAR(128) NOT NULL,          -- 所属知识库 ID
    title           VARCHAR(512) NOT NULL,          -- 文档标题
    node_type       VARCHAR(16) DEFAULT 'FILE',     -- FILE / FOLDER
    parent_id       VARCHAR(128) DEFAULT '',        -- 父节点 ID
    content         TEXT DEFAULT '',                -- 解析后的 Markdown 正文
    raw_json        TEXT DEFAULT '',                -- 钉钉 API 原始返回 JSON
    synced_at       DATETIME,                       -- 最后同步时间
    created_at      DATETIME,                       -- 首次创建时间
    updated_at      DATETIME,                       -- 最后更新时间

    INDEX idx_kb_docs_workspace (workspace_id),
    INDEX idx_kb_docs_parent (parent_id)
);
```

### 数据来源

```
钉钉 API /v1.0/doc/.../blocks  →  parser.py: blocks_to_markdown()
                            →  _cache_document()
                            →  INSERT / UPDATE kb_documents
```

### 数据形态

- **FILE 节点**：有 `content`（Markdown）、有 `raw_json`（钉钉原始返回）
- **FOLDER 节点**：仅元数据，`content` 为空，`raw_json` 含目录信息
- 文档更新时 **整行覆盖**（`synced_at` + `content`），不做 diff

### 使用场景

- `GET /ai/knowledge/documents/<node_id>` — cache-first 读取
- `POST /ai/knowledge/sync` — 批量写入
- 切片时读取 `content` 字段作为 `chunker.py` 输入

---

## 3. kb_chunks — 文档切片表

### 表结构

```sql
CREATE TABLE kb_chunks (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    doc_id          VARCHAR(128) NOT NULL,          -- 源文档 doc_id
    chunk_index     INT NOT NULL,                   -- 切片序号（从 0 开始）
    content         TEXT NOT NULL,                  -- 切片文本（含元数据前缀）
    token_count     INT DEFAULT 0,                  -- token 数（tiktoken cl100k_base）
    created_at      DATETIME,

    INDEX idx_kb_chunks_doc (doc_id, chunk_index),
    FULLTEXT INDEX ft_kb_chunks_content (content)   -- MySQL 全文检索
);
```

### 数据来源（Phase 2 实现）

```
kb_documents.content (整篇 Markdown)
    ↓ chunker.py: 按 ## 标题切分 + 类型感知
    ↓ 注入元数据前缀
    ↓ tiktoken 计数
    ↓ INSERT INTO kb_chunks
    ↓ 触发 FULLTEXT INDEX 更新
```

### 切片格式

每片 `content` 包含元数据前缀 + 正文：

```
[来源: 本体开发部 > 技术三组 > 订单项目 > 支付模块设计规范]
[章节: ## 3.2 支付回调超时处理]

正文内容...
```

### 切片规则

| 文档类型 | 识别方式 | 切分策略 | 目标粒度 |
|---------|---------|---------|---------|
| 规范/设计文档 | `##` 层级标题 | 按 `##` 切分 | 800-1000 token |
| 会议纪要/周报 | 标题或路径关键词 | 段落聚合 | 500-800 token |
| 表格 (.axls) | node_type=WORKBOOK | 行分组+表头 | 20-30 行/片 |
| 纯文本/其他 | fallback | 固定窗口滑动 | 800 token |

- 相邻切片重叠 150 token
- 最小值 100 token（低于此合并到上一片）
- 如 `##` 区间 > 1000 token，下沉按 `###` 再切

### 重新切片

```sql
-- 文档内容更新后，先删旧切片再切新片
DELETE FROM kb_chunks WHERE doc_id = ?;
-- 重新切片时 FTS 索引自动同步（外部内容表模式）
```

---

## 4. MySQL FULLTEXT INDEX — 关键词检索

### 创建

```sql
ALTER TABLE kb_chunks ADD FULLTEXT INDEX ft_kb_chunks_content (content) WITH PARSER ngram;
```

> 必须用 ngram parser，MySQL 默认分词器不认中文，中文全被拆成单字节，低于 `min_token_size=3` 无法索引。

### 检索方式

```sql
-- 自然语言模式
SELECT *, MATCH(content) AGAINST('支付回调 超时处理') AS score
FROM kb_chunks
WHERE MATCH(content) AGAINST('支付回调 超时处理')
ORDER BY score DESC
LIMIT 10;

-- 布尔模式（更精确）
SELECT *, MATCH(content) AGAINST('+支付 +回调 超时' IN BOOLEAN MODE) AS score
FROM kb_chunks
WHERE MATCH(content) AGAINST('+支付 +回调 超时' IN BOOLEAN MODE)
LIMIT 10;
```

### 限制

- InnoDB 默认最小词长 3（`innodb_ft_min_token_size=3`），中文需分词
- 搜索结果由 `NATURAL_LANGUAGE_MODE` 评分决定
- 作为混合检索的**关键词路**，与 pgvector 语义路互补

---

## 5. pgvector — 语义向量检索

### 连接信息

```python
# db/config.py
PGVECTOR_DATABASE_URI = "postgresql+psycopg2://tb:xxx@127.0.0.1:5432/kb_vectors"
```

环境变量：`PGVECTOR_HOST`, `PGVECTOR_PORT`, `PGVECTOR_USER`, `PGVECTOR_PASSWORD`, `PGVECTOR_DB`

### 部署

```bash
docker-compose up -d   # pgvector/pgvector:pg16 容器
```

### 表设计（Phase 3 实现）

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE chunk_vectors (
    id          SERIAL PRIMARY KEY,
    chunk_id    INTEGER NOT NULL,       -- 对应 kb_chunks.id (MySQL)
    embedding   vector(1536),           -- text-embedding-3-small 维度
    created_at  TIMESTAMP DEFAULT NOW()
);

-- HNSW 索引（构建快、查询快、召回率高）
CREATE INDEX ON chunk_vectors USING hnsw (embedding vector_cosine_ops);
```

### 检索方式

```sql
-- 余弦相似度检索
SELECT chunk_id, 1 - (embedding <=> $query_vector) AS similarity
FROM chunk_vectors
ORDER BY embedding <=> $query_vector
LIMIT 20;
```

---

## 6. 混合检索流程

```
用户问题: "支付回调怎么处理超时？"
    │
    ├─→ MySQL FULLTEXT: MATCH(content) AGAINST('支付 回调 超时')
    │   → top-10 切片
    │
    └─→ One-API embedding: POST /v1/embeddings
        → pgvector: ORDER BY embedding <=> $query_vector LIMIT 20
        → top-20 切片
              │
              ▼
         RRF 融合 + 去重 + 排序 → top-8
              │
              ▼
         从 kb_chunks.content 取切片文本
         + 从 kb_documents.title 取来源标题
              │
              ▼
         Prompt 拼接 → LLM (SSE 流式)
```

| 参数 | 值 |
|------|-----|
| 全文检索 top-N | 10 |
| 向量检索 top-N | 20 |
| 最终 top-K | 8 |
| 单片段最大 token | 800 |
| 总召回 token 上限 | 4000 |
| embedding 模型 | text-embedding-3-small |
| 向量维度 | 1536 |
| pgvector 索引 | HNSW (cosine) |

---

## 7. 表关系总览

```
kb_documents (1)
    │
    │ doc_id
    │
    └── kb_chunks (N)
            │
            │ id (MySQL)  ←→  chunk_id (PostgreSQL)
            │
            └── chunk_vectors (N)  [PostgreSQL + pgvector]

MySQL tb_management         PostgreSQL kb_vectors
├── kb_documents            └── chunk_vectors
│   └── MARKDOWN 正文
├── kb_chunks
│   ├── 切片文本
│   └── FULLTEXT INDEX
└── ... (其他业务表)

docker-compose
└── pgvector/pgvector:pg16 (端口 5432)
```

## 8. 同步 → 切片 → 向量化 流水线

```
POST /ai/knowledge/sync
    │ 遍历钉钉知识库树
    │ blocks_to_markdown()
    │ INSERT/UPDATE kb_documents
    ▼

POST /ai/knowledge/rechunk
    │ 读取 kb_documents.content
    │ chunker.py 切片
    │ INSERT kb_chunks
    │ MySQL FULLTEXT INDEX 自动更新
    ▼

POST /ai/knowledge/reembed  (Phase 3)
    │ 读取 kb_chunks.content
    │ POST /v1/embeddings
    │ INSERT chunk_vectors (PostgreSQL)
    │ HNSW 索引自动更新
    ▼
    可检索
```
