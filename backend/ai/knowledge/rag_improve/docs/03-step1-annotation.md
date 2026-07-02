# Step 1: 测试集构建（已完成）

## 方法：TREC 标准 Pooling + LLM 辅助标注

采用信息检索领域经典的 **TREC Pooling 范式**，结合 LLM 做 relevance judgment。

### 流程

```
对每道题：
  1. Pooling 三路检索（各取 top-15）：
     ├── FTS 关键词检索（MySQL FULLTEXT）
     ├── 向量语义检索（pgvector cosine）
     └── Hybrid 混合检索（RRF 融合）
     
  2. 三路结果合并去重 → 候选池（约 30~40 条）
  
  3. 候选池内容 + 题目 → deepseek-v4-pro (temperature=0)
  
  4. LLM 返回相关的 chunk_id 列表 → 写入 relevant_chunk_ids
```

### 为什么用 Pooling

单个检索系统的结果有偏见——它搜不到的不代表不相关。TREC/BEIR 等学术基准的标准做法是合并多个系统的结果形成候选池，再做 relevance judgment。这保证了标准答案不会被任何一种检索方式的盲区漏掉。

### 参数配置

| 参数 | 值 |
|------|-----|
| 三路各自 top-k | 15 |
| 候选池大小 | 约 30~40 条 |
| chunk 截断长度 | 800 字符 |
| LLM 模型 | deepseek-v4-pro (via one-api) |
| temperature | 0.0 |
| 测试题数量 | 26 条（135 个标注 chunk，0 空题） |
| 测试题类型 | 技术文档(10) / 会议纪要(7) / 表格(4) / 跨文档(5) |
| 难度分布 | easy(6) / medium(12) / hard(8) |

### 脚本

- `step01_build_testset.py` — 执行标注
- 运行：`python -m ai.knowledge.rag_improve.step01_build_testset`

### 人工复核

标注完成后抽检 5~10 条，验证 LLM 判断质量。

---

## 待确认

1. [x] **方法**：TREC Pooling（三路检索合并）
2. [x] **候选数量**：每路 top-15，合并约 30~40
3. [x] **LLM 模型**：deepseek-v4-pro
4. [x] **人工复核**：标完后抽检
5. [x] **覆盖策略**：全量覆盖
6. [x] **测试题**：26 条，含"自学习精度优化"
