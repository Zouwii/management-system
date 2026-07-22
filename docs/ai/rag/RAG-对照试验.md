# RAG 对照试验

> 整合自：retrieval-benchmark、fidelity-experiment、rag-experiments

---

## 1. 检索优化对照试验

### 基线链路

```
用户问题 → Hybrid检索(FTS关键词 + bge-small向量 → RRF融合) → 返回chunks
```

| 环节 | 方案 |
|------|------|
| 分块 | 4策略自适应 (structured / meeting / table / text) |
| 嵌入 | BGE-small-zh-v1.5 (512d) |
| 关键词 | MySQL FULLTEXT / SQLite FTS5 (BM25) |
| 向量检索 | pgvector cosine |
| 融合 | RRF (k=60) |
| 重排 | 无 |

### 实验组

| 组别 | 嵌入模型 | 检索 | 重排 |
|------|----------|------|------|
| A (基线) | bge-small-zh-v1.5 (512d) | Hybrid RRF | 无 |
| B | bge-small-zh-v1.5 (512d) | Hybrid RRF | bge-reranker-v2-m3 |
| C | bge-m3 (1024d) | 纯向量 | 无 |

### 评测指标

- **NDCG@5 / NDCG@10**: 排序质量
- **Recall@5 / Recall@10**: 召回率
- **MRR**: Mean Reciprocal Rank
- **Hit Rate**: 至少命中一个正确答案的比例

### 测试集

- 基于 TREC Pooling 方法构建
- LLM 辅助标注 + 人工校验
- 覆盖知识库各模块：导航、对接、调度、标定等

### 结果

| 指标 | A (baseline) | B (+reranker) | C (bge-m3) |
|------|-------------|---------------|------------|
| NDCG@5 | 0.47 | 0.63 | 0.55 |
| Recall@5 | 0.52 | 0.68 | 0.60 |
| MRR | 0.51 | 0.71 | 0.58 |

> **结论**：B 组（baseline + reranker）提升最大，bge-m3 单独替换提升有限。

---

## 2. 保真度实验

### 问题

当前链路存在信息丢失：

- 图片、流程图、截图等非文本信息未入索引
- `blocks_to_markdown()` 对媒体类 block 无处理
- `kb_chunks` 缺少结构化字段 (heading, path, chunk_type)

### 实验目标

1. 完整保存原始 DingTalk blocks
2. 识别并统计图片/附件/媒体 block
3. Markdown 中保留图片占位符
4. 评估保真度对检索质量的影响

### 方法

```
完整 blocks → block_manifest.json (block类型统计)
           → asset_manifest.json (图片/附件清单)
           → fidelity_report.md (保真度报告)
```

### 结论

实验进行中。初步发现约 15% 的文档包含图片/附件等非文本信息。

---

## 3. 测试集构建方法论

基于 TREC / BEIR 标准：

1. **Pooling**: 用多种检索策略收集候选文档池
2. **LLM 标注**: GPT-4 判断相关性 (0-3 分)
3. **人工校验**: 抽样验证 LLM 标注质量
4. **最终集合**: 约 150 条 query，覆盖 8 个知识域
