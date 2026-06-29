# RAG 检索对照试验工作台

> 6 项工作，按依赖顺序执行。每完成一项打勾。

---

## 工作清单

### [x] 1. 标注测试集 ✅ 完成

**方法**: TREC Pooling（三路检索合并）+ LLM relevance judgment + 人工复核

**文件**: `test_queries.json`（26 条查询，`relevant_chunk_ids` 已标注）

**脚本**: `llm_label.py` — 执行标注
```bash
python -m ai.knowledge.rag_improve.llm_label
```

**文档**: `docs/step1-annotation.md` — 完整方法说明
**参考**: `docs/how-to-build-testset.md` — 业界标准做法对比

---

### [ ] 2. 建新向量表 + 安装模型

**建表 SQL** (在 pgvector 库执行):
```sql
CREATE TABLE IF NOT EXISTS chunk_vectors_bgem3 (
    id SERIAL PRIMARY KEY,
    chunk_id INTEGER NOT NULL UNIQUE,
    embedding vector(1024),
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_cv_bgem3_ivfflat
    ON chunk_vectors_bgem3 USING ivfflat (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS chunk_vectors_large (
    id SERIAL PRIMARY KEY,
    chunk_id INTEGER NOT NULL UNIQUE,
    embedding vector(1024),
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_cv_large_ivfflat
    ON chunk_vectors_large USING ivfflat (embedding vector_cosine_ops);
```

**安装模型**:
```bash
pip install sentence-transformers>=3.0 FlagEmbedding
# 模型首次加载自动下载到 ~/.cache/huggingface/
# bge-m3 ~2.2GB, bge-large ~1.3GB, reranker-v2-m3 ~1.1GB, reranker-large ~2.2GB
```

---

### [ ] 3. 批量编码存量 chunk → 新向量表

**文件**: `encode_vectors.py`（待开发）

用 bge-m3 和 bge-large 分别编码 11528 条 chunk，写入 `chunk_vectors_bgem3` 和 `chunk_vectors_large`。

---

### [ ] 4. 实现 5 组检索策略

**文件**: `strategies.py`（待开发）

| 组 | 嵌入模型 | 检索方式 | 重排 | 向量表 |
|----|---------|---------|------|--------|
| A | bge-small 512d | Hybrid RRF | 无 | chunk_vectors ✅ |
| B | bge-small 512d | Hybrid RRF | bge-reranker-v2-m3 | chunk_vectors ✅ |
| C | bge-m3 1024d | 纯向量 dense+sparse | 无 | chunk_vectors_bgem3 |
| D | bge-m3 1024d | 纯向量 | bge-reranker-v2-m3 | chunk_vectors_bgem3 |
| E | bge-large 1024d | Hybrid RRF | bge-reranker-large | chunk_vectors_large |

---

### [ ] 5. 实现评估指标

**文件**: `metrics.py`（待开发）

- Recall@5: 前 5 条命中正确答案的比例
- MRR: 第一个正确答案排名的倒数均值
- nDCG@5: 归一化折损累积增益

---

### [ ] 6. 跑实验 + 输出报告

**文件**: `runner.py`（待开发）

对 5 组策略跑全部 25 题，输出对比表：
- 总表：5 组 × 3 指标
- 细分表：按查询类型（技术文档/会议/表格/跨文档）
- 最终推荐方案

---

## 目录结构

```
rag_improve/
├── README.md              ← 你正在看的
├── test_queries.json      ← 标注测试集 (25条)
├── annotate.py            ← 交互式标注工具
├── docs/
│   ├── 13-rag-retrieval-benchmark.md   ← 对照试验方案设计
│   └── 10-RAG检索调研与优化方案.md      ← RAG 全景调研
├── encode_vectors.py      ← [待开发] 批量编码
├── strategies.py          ← [待开发] 5 组检索策略
├── metrics.py             ← [待开发] 评估指标
└── runner.py              ← [待开发] 评测主程序
```

---

## 面试素材

> 我对 RAG 检索质量做了系统的 A/B 对照试验，构建了 25 条标注测试集覆盖 4 种查询类型，
> 对比了 5 种策略组合（基线/加重排/换模型/叠加），用 Recall@5、MRR、nDCG@5 做横向对比。
> 最终选型基于数据而非直觉 —— XX 方案相比基线 recall 提升了 XX%。
