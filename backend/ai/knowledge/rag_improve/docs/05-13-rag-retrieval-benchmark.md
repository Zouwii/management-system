# RAG 检索优化对照试验方案

> **实际执行情况**：2026-06-29 已完成 A vs B 对照实验。实验暴露了 Hybrid RRF 融合缺陷，B 组策略已改进为双路召回 + 重排。C/D/E 组后续推进。

---

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

| 组别 | 嵌入模型 | 检索方式 | 重排 | 向量表 | 状态 |
|------|----------|----------|------|--------|------|
| **A（基线）** | bge-small 512d | Hybrid RRF | 无 | `chunk_vectors` | ✅ 已跑 |
| **B** | bge-small 512d | **双路召回**（Hybrid RRF + 纯向量） | `bge-reranker-v2-m3` | `chunk_vectors` | ✅ 已跑 |
| **C** | bge-m3 1024d | 纯向量（dense+sparse合一） | 无 | `chunk_vectors_bgem3` | 后续 |
| **D** | bge-m3 1024d | 纯向量 | `bge-reranker-v2-m3` | `chunk_vectors_bgem3` | 后续 |
| **E** | bge-large 1024d | Hybrid RRF | `bge-reranker-large` | `chunk_vectors_large` | 后续 |

### 2.2 对照逻辑

- **B vs A**：验证 reranker + 双路召回的效果 ✅
- **C vs A**：验证 bge-m3 替代 "bge-small + FTS" 的效果
- **D vs C**：验证 bge-m3 + reranker 叠加
- **E vs A**：验证大模型全套极致效果

### 2.3 B 组双路召回设计（v2）

原始设计：Hybrid RRF top-20 → Cross-Encoder → top-N

实验发现问题：当 FTS 关键词与向量分歧大时，RRF 会**稀释**向量侧好结果。实测案例：
- chunk 1224：向量排 #15 ✅ → RRF 后 #35 ❌ → 连 top-20 候选池都没进

改进为双路召回：

```
Hybrid RRF top-20    纯向量 top-20
       ↓                   ↓
    合并去重 → ~35 候选 → Cross-Encoder → top-5
```

向量独立走 pgvector，不受 RRF 影响，确保语义匹配的 chunk 必然进候选池。

### 2.4 数据隔离

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

26 条标注测试集，覆盖 4 类（详见 `test_queries.json`）：

| 类型 | 数量 | 难度分布 |
|------|------|---------|
| 技术文档 | 10 | easy 2 / medium 5 / hard 3 |
| 会议纪要 | 7 | easy 3 / medium 2 / hard 2 |
| 表格数据 | 4 | easy 2 / medium 1 / hard 1 |
| 跨文档 | 5 | easy 0 / medium 3 / hard 2 |

方法：TREC Pooling（三路检索合并）+ LLM-as-Judge（deepseek-v4-pro, temperature=0）。详见 `02-how-to-build-testset.md`。

### 4.2 标注格式

```json
{
  "id": 1,
  "query": "导航算法主要流程",
  "relevant_chunk_ids": [42, 87, 103],
  "source_docs": ["导航算法设计.adoc"],
  "type": "技术文档",
  "difficulty": "easy",
  "note": "直接从导航算法设计文档中找到"
}
```

## 5. 实验结果

> 实验日期：2026-06-29 | 测试集：26 题 | 三版迭代

### 5.1 汇总对比

| 版本 | 策略 | 重排模型 | Recall@5 | MRR | nDCG@5 | 延迟 | 结论 |
|------|------|---------|----------|-----|--------|------|------|
| A | 基线 | — | 34.1% | 0.559 | 0.385 | 0.04s | 起点 |
| v1 | 单路 Hybrid | v2-m3 (2.2GB) | **63.3%** | **0.764** | **0.698** | 38s | 精度最高，延迟不可用 |
| v2 | 双路召回 | v2-m3 (2.2GB) | 60.0% | 0.701 | 0.643 | 40s | 双路噪音反噬，证伪 |
| **v3** | **单路 Hybrid** | **base (280MB)** | **59.6%** | **0.697** | **0.622** | **5s (CPU)** | **当前硬件最优** ✅ |

### 5.2 v3 推荐方案（单路 Hybrid + bge-reranker-base）

> 运行：`python -m ai.knowledge.rag_improve.step05_runner --output results_v3_base.json`

**整体**

| 组别 | Recall@5 | MRR | nDCG@5 |
|------|----------|-----|--------|
| A（基线） | 34.1% | 0.559 | 0.385 |
| B（base reranker） | **59.6%** | **0.697** | **0.622** |
| 提升 | +25.5pp (+74.8%) | +0.138 | +0.237 |

**按查询类型**

| 类型 | ΔRecall@5 | ΔMRR | ΔnDCG@5 |
|------|-----------|------|---------|
| 会议纪要 | +47.6pp | +0.167 | +0.334 |
| 技术文档 | +20.6pp | +0.117 | +0.204 |
| 表格 | +14.3pp | +0.075 | +0.165 |
| 跨文档 | +13.1pp | +0.190 | +0.225 |

**按难度**

| 难度 | ΔRecall@5 | ΔMRR | ΔnDCG@5 |
|------|-----------|------|---------|
| easy | +32.9pp | +0.111 | +0.331 |
| medium | +20.3pp | +0.086 | +0.169 |
| hard | +27.6pp | +0.235 | +0.269 |

**逐题**：▲15 —8 ▼3（#5, #8, #23 下降），#24/#26 仍为 0

### 5.3 v1 历史参考（单路 Hybrid + v2-m3）

| 组别 | Recall@5 | MRR | nDCG@5 |
|------|----------|-----|--------|
| A（基线） | 34.1% | 0.559 | 0.385 |
| B（v2-m3） | 63.3% | 0.764 | 0.698 |
| 提升 | +29.2pp (+85.6%) | +0.205 | +0.313 |

| 类型 | ΔRecall@5 | ΔMRR | ΔnDCG@5 |
|------|-----------|------|---------|
| 会议纪要 | +47.6pp | +0.231 | +0.399 |
| 技术文档 | +28.5pp | +0.267 | +0.341 |
| 表格 | +17.9pp | -0.050 | +0.170 |
| 跨文档 | +14.0pp | +0.250 | +0.253 |

逐题：▲18 —6 ▼2（#20 下降, #24/#26 为 0）

### 5.4 已知问题

1. **RRF 稀释**：Hybrid RRF (k=60) 在 FTS 与向量分歧大时拖累向量好结果。双路召回未能解决（chunk 进候选池但 reranker 未排入 top-5）
2. **P1000 GPU 瓶颈**：2.2GB 模型 GPU 推理反比 CPU 慢 2.5x，小模型 base 是甜点
3. **表格 MRR 微降**：-0.050 (v1) / +0.075 (v3)，重排对表格语义增益有限
4. **自学习文档覆盖不足**：#24/#26 标注 chunk 仅 1-2 条，三版均 0

### 5.5 服务器实测（2026-06-30）

> 服务器：172.19.3.79, i7-11700 8C/16T, 62GB RAM, GPU 不可用（驱动故障）

| 模型 | 单对 | 20候选预估 | Recall@5 | 大小 |
|------|------|----------|----------|------|
| bge-reranker-base | **45ms** | **~0.9s** ✅ | 59.6% | 280MB |
| bge-reranker-v2-m3 | 160ms | ~2-3s | 63.3% | 2.2GB |

**部署**：默认 base（~1s/query），`reranker_model="v2-m3"` 一键切高精度模式。

---

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
