# RAG 系统设计

> 整合自：knowledge-service-design、kb-database-design、knowledge-base-rag

---

## 1. 系统概览

```
用户提问 → 关键词提取 → 本地切块搜索(kb_chunks) → CrossEncoder重排 → LLM生成答案
```

### 核心组件

| 组件 | 文件 | 职责 |
|------|------|------|
| 同步 | `auto_sync.py` | 定期从钉钉拉文档，解析为 Markdown |
| 切分 | `chunker.py` | 滑动窗口切块 (chunk_size=512, overlap=128) |
| 嵌入 | `embedder.py` | BGE-large-zh-v1.5 → pgvector |
| 检索 | `retriever.py` | hybrid search (关键词 + 向量) |
| 重排 | `reranker.py` | BGE-reranker-v2-m3 精排 top-k |
| 问答 | `chat.py` | SSE 流式，带引用来源 |

### 数据流

```
钉钉知识库 ──sync──→ kb_documents (MySQL)
                        │
                    chunker.py
                        │
                      kb_chunks (MySQL)
                        │
                    embedder.py
                        │
                    pgvector (embeddings)
                        │
                    检索 + 重排 + LLM
```

---

## 2. 数据库设计

### kb_documents — 文档元数据

| 字段 | 类型 | 说明 |
|------|------|------|
| doc_id | VARCHAR(128) UNIQUE | 钉钉 nodeId |
| workspace_id | VARCHAR(128) | 知识库 ID |
| title | VARCHAR(512) | 文档标题 |
| content | MEDIUMTEXT | 解析后的 Markdown 正文 |
| category | VARCHAR(16) | ALIDOC / WORKBOOK |
| breadcrumb | VARCHAR(1024) | 面包屑路径 |
| parent_id | VARCHAR(128) | 父节点 ID |
| raw_json | TEXT | API 原始返回 |
| synced_at | DATETIME | 同步时间 |

### kb_chunks — 文档切片

| 字段 | 类型 | 说明 |
|------|------|------|
| doc_id | VARCHAR(128) | 关联文档 |
| chunk_index | INT | 切片序号 |
| content | TEXT | 切片文本，含 `[来源: xx] [章节: yy]` 标记 |
| token_count | INT | token 数 |

**索引**：FULLTEXT (ngram) + 普通索引 (doc_id, chunk_index)

### pgvector — 向量存储

```sql
CREATE TABLE kb_embeddings (
    id SERIAL PRIMARY KEY,
    chunk_id INT REFERENCES kb_chunks(id),
    embedding vector(1024)
);
CREATE INDEX ON kb_embeddings USING ivfflat (embedding vector_cosine_ops);
```

---

## 3. 检索策略

### 混合检索

| 阶段 | 方法 | 说明 |
|------|------|------|
| 关键词检索 | MySQL FULLTEXT (ngram) | BOOLEAN MODE，中文分词 |
| 向量检索 | pgvector cosine | BGE-large-zh-v1.5 (1024d) |
| 重排 | BGE-reranker-v2-m3 | top-20 → rerank → top-5 |

### 参数

```
keyword_top_k: 10
vector_top_k:  10
rerank_top_k:   5
chunk_size:    512 tokens
overlap:       128 tokens
```

---

## 4. 知识库服务

### API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/ai/knowledge/workspaces` | 列出所有知识库 |
| GET | `/ai/knowledge/workspaces/<id>/nodes` | 浏览文档树 |
| GET | `/ai/knowledge/documents/<node_id>` | 获取文档内容 |
| POST | `/ai/knowledge/chunks/search` | 本地切片搜索 |
| POST | `/ai/knowledge/chat/session` | 创建问答会话 |
| GET | `/ai/knowledge/chat` | SSE 流式问答 |

### 同步策略

- 定时任务 (`auto_sync.py`)，默认每天凌晨
- 只同步 FILE 类型（不存 FOLDER）
- `sync_disabled` 文件可暂停同步

---

## 5. 已知局限

1. **不递归** — 只拉文件夹直接子文件，子文件夹内容跳过
2. **不存文件夹** — `parent_id` 指向钉钉侧 nodeId，库内无法解析目录名
3. **content 可能空** — 同步时可选是否下载正文
4. **errcode_documents 独立** — 错误码内容单独建表，未与主库打通
