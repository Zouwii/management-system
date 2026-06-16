# RAG 检索优化对照试验方案

## 1. 背景

当前知识库检索链路：

```
用户问题 → Hybrid 检索（FTS关键词 + bge-small向量 → RRF融合） → 返回 chunks
```

各环节现状：

| 环节 | 方案 | 详情 |
|------|------|------|
| 分块 | 4策略自适应 | structured / meeting / table / text |
| 嵌入 | `BAAI/bge-small-zh-v1.5` | 512维，SentenceTransformer |
| 关键词 | MySQL FULLTEXT / SQLite FTS5 | BM25 评分 |
| 向量检索 | pgvector cosine | `embedding <=> query_vec` |
| 融合 | RRF (k=60) | `score = Σ 1/(k + rank_i)` |
| 重排 | 无 | - |

## 2. 实验设计

### 2.1 实验组

| 组别 | 嵌入模型 | 检索方式 | 重排 | 向量表 |
|------|----------|----------|------|--------|
| **A（基线）** | bge-small-zh-v1.5 (512d) | Hybrid RRF | 无 | `chunk_vectors` |
| **B** | bge-small-zh-v1.5 (512d) | Hybrid RRF | `bge-reranker-v2-m3` | `chunk_vectors` |
| **C** | bge-m3 (1024d) | 纯向量（dense+sparse合一） | 无 | `chunk_vectors_bgem3` |
| **D** | bge-m3 (1024d) | 纯向量 | `bge-reranker-v2-m3` | `chunk_vectors_bgem3` |
| **E** | bge-large-zh-v1.5 (1024d) | Hybrid RRF | `bge-reranker-large` | `chunk_vectors_large` |

### 2.2 对照逻辑

- **B vs A**：单独验证 reranker 的效果
- **C vs A**：验证 bge-m3 替代 "bge-small + FTS" 的效果
- **D vs C**：验证 bge-m3 + reranker 叠加
- **E vs A**：验证大模型全套极致效果

### 2.3 数据隔离

各组向量独立建表，共用同一份 `kb_chunks`，互不影响：

```
chunk_vectors          — A、B 组（bge-small, 512d，已存在）
chunk_vectors_bgem3    — C、D 组（bge-m3, 1024d）
chunk_vectors_large    — E 组（bge-large, 1024d）
```

## 3. 评估指标

| 指标 | 公式 / 含义 |
|------|------------|
| **Recall@5** | 前5条命中正确答案 chunk_id 的比例 |
| **MRR** (Mean Reciprocal Rank) | `1/第一个正确答案的排名`，越靠近1越好 |
| **nDCG@5** | 考虑排名的综合相关性评分 |

## 4. 测试集构建

### 4.1 查询分类

从实际场景收集 20~30 条查询，覆盖 4 类：

| 类型 | 数量 | 示例 |
|------|------|------|
| 技术文档 | 5~8 | "本体架构是怎样的" |
| 会议纪要 | 5~8 | "上周周会讨论了什么" |
| 表格数据 | 3~5 | "Q1 各小组工时" |
| 跨文档 | 3~5 | 需多文档拼凑的问题 |

### 4.2 标注格式

```json
{
  "query": "导航算法主要流程",
  "relevant_chunk_ids": [42, 87, 103],
  "source_docs": ["导航算法设计.md"],
  "difficulty": "easy"
}
```

- `relevant_chunk_ids`：人工标注正确 chunk
- `difficulty`：easy / medium / hard

## 5. 实施步骤

### Step 1：标注测试集（`test_queries.json`）

1. 从 `kb_chunks` 导出所有 chunk 内容
2. 收集 20 条典型用户问题
3. 人工标注每题正确答案 chunk_id

### Step 2：安装模型

```bash
pip install sentence-transformers>=3.0 FlagEmbedding
```

模型文件（建议提前下载到本地）：

| 模型 | 大小 | HuggingFace |
|------|------|-------------|
| bge-small-zh-v1.5 | ~100MB | BAAI/bge-small-zh-v1.5 |
| bge-m3 | ~2.2GB | BAAI/bge-m3 |
| bge-large-zh-v1.5 | ~1.3GB | BAAI/bge-large-zh-v1.5 |
| bge-reranker-v2-m3 | ~1.1GB | BAAI/bge-reranker-v2-m3 |
| bge-reranker-large | ~2.2GB | BAAI/bge-reranker-large |

### Step 3：建向量表

```sql
-- C、D 组：bge-m3, 1024维
CREATE TABLE IF NOT EXISTS chunk_vectors_bgem3 (
    id SERIAL PRIMARY KEY,
    chunk_id INTEGER NOT NULL UNIQUE,
    embedding vector(1024),
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_cv_bgem3_ivfflat
    ON chunk_vectors_bgem3 USING ivfflat (embedding vector_cosine_ops);

-- E 组：bge-large, 1024维
CREATE TABLE IF NOT EXISTS chunk_vectors_large (
    id SERIAL PRIMARY KEY,
    chunk_id INTEGER NOT NULL UNIQUE,
    embedding vector(1024),
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_cv_large_ivfflat
    ON chunk_vectors_large USING ivfflat (embedding vector_cosine_ops);
```

### Step 4：批量编码现存数据

```python
from sentence_transformers import SentenceTransformer, FlagEmbedding

CHUNKS = get_all_chunks()  # SELECT id, content FROM kb_chunks

for cfg in [
    {"name": "m3",    "model": "BAAI/bge-m3",            "table": "chunk_vectors_bgem3", "dim": 1024},
    {"name": "large", "model": "BAAI/bge-large-zh-v1.5", "table": "chunk_vectors_large", "dim": 1024},
]:
    model = SentenceTransformer(cfg["model"])
    for batch in chunked(CHUNKS, 32):
        vecs = model.encode([c.content for c in batch], normalize_embeddings=True)
        insert_vectors(cfg["table"], [(c.id, v) for c, v in zip(batch, vecs)])
```

### Step 5：评测脚本骨架

```python
def evaluate_group(group, test_queries):
    """对一组配置跑全部测试题，返回平均指标"""
    rec5, mrr_vals, ndcg5 = [], [], []
    for q in test_queries:
        results = retrieve(q["query"], group)        # 各组不同检索逻辑
        rec5.append(recall_at_k(results, q["relevant_chunk_ids"], 5))
        mrr_vals.append(mrr(results, q["relevant_chunk_ids"]))
        ndcg5.append(ndcg_at_k(results, q["relevant_chunk_ids"], 5))
    return {
        "recall@5": mean(rec5),
        "mrr": mean(mrr_vals),
        "ndcg@5": mean(ndcg5),
    }

for group_name, config in GROUPS.items():
    metrics = evaluate_group(config, test_queries)
    print(f"{group_name}: R@5={metrics['recall@5']:.3f} "
          f"MRR={metrics['mrr']:.3f} nDCG@5={metrics['ndcg@5']:.3f}")
```

### Step 6：输出报告

对比表 + 按问题类型细分 + 最终推荐。

## 6. 预期结论模板

| 组别 | Recall@5 | MRR | nDCG@5 | 解读 |
|------|----------|-----|--------|------|
| A（基线） | - | - | - | 当前生产方案 |
| B | - | - | - | 加 reranker 的效果 |
| C | - | - | - | 换 bge-m3 的效果 |
| D | - | - | - | m3+reranker |
| E | - | - | - | 大杯全套 |

## 7. 模型 API 说明

### bge-m3：单一模型，双路输出

```python
from FlagEmbedding import BGEM3FlagModel

model = BGEM3FlagModel("BAAI/bge-m3", use_fp16=True)
out = model.encode(["查询"], return_dense=True, return_sparse=True)

dense  = out["dense_vecs"][0]         # (1024,) numpy array
sparse = out["lexical_weights"][0]    # {token_id: weight} 类似 BM25
```

bge-m3 天然支持混合检索，不需要单独跑 FTS。

### bge-reranker：精排

```python
from FlagEmbedding import FlagReranker

reranker = FlagReranker("BAAI/bge-reranker-v2-m3", use_fp16=True)
scores = reranker.compute_score([
    ["查询文本", "候选chunk 1"],
    ["查询文本", "候选chunk 2"],
])
```

## 8. 注意事项

1. 模型首次加载需联网，生产环境可提前下载到本地目录
2. bge-m3 约 2.2GB，reranker 约 1.1GB，需足够内存/显存
3. pgvector 需 `CREATE EXTENSION vector`（如未启用）
4. ivfflat 索引需 `VACUUM ANALYZE` 表后才生效
5. 各组向量表独立，可随时重建，不影响在线服务
