# RAG 测试集构建：正确方法论

> 参考资料：BEIR (NeurIPS 2021)、RAGAS、TREC 评估范式、MTEB

---

## 业界标准做法

### 方法一：TREC / BEIR 范式（学术金标准）

学术界评估检索系统的标准流程：

```
1. 定义信息需求（Information Need）
   → 从真实场景收集用户可能问的问题（20~50 条）

2. Pooling（结果池化）
   → 用多个不同的检索系统各搜 top-N
   → 把所有系统的结果合并去重 → 形成"候选池"
   → 目的：避免某个系统的偏见——它搜不到的不代表不相关

3. 人工标注（Relevance Judgment）
   → 标注员逐条判断候选池中每个 chunk 对 query 的相关性
   → 通常用 0-3 分级：不相关 / 略微相关 / 相关 / 高度相关

4. 计算指标
   → Recall@K、MRR、nDCG@K
```

**关键点：Pooling。** 单个系统的检索结果有偏见——它搜不到的不代表不相关。

### 方法二：RAGAS 范式（LLM 辅助，工业界主流）

RAGAS（ Retrieval Augmented Generation Assessment）的核心创新是**参考无关评估**：

```
1. 测试集生成（Synthetic Test Generation）
   → LLM 从知识库文档中自动生成<问题, 答案>对
   → 不需要人工出题

2. LLM-as-Judge 评估
   → context_precision：检索到的 chunk 中相关的比例
   → context_recall：正确答案所需的信息是否都被检索到
   → faithfulness：生成的答案是否忠于检索到的内容
   → answer_relevancy：答案是否直接回答了问题

3. 不需要人工标注 ground truth
```

**关键点：完全自动化。** 但依赖 LLM 判断质量——LLM 可能判错，需要温度设 0 并抽样验证。

### 方法三：混合方案（推荐）

结合两者优点：

```
1. 人工出题（确保覆盖真实场景）
   → 覆盖不同文档类型、不同难度

2. LLM 辅助标注（替代人工判 relevance）
   → Pooling 多系统结果 → LLM 逐条判相关性
   → 人工抽检 20% 验证 LLM 判断质量

3. 多指标评估
   → Recall@K + MRR + nDCG（经典 IR 指标）
   → 按查询类型细分（技术文档/会议/表格/跨文档）
```

---

## 当前我们的做法 vs 标准做法

| 环节 | 标准做法 | 我们当前的做法 | 差距 |
|------|---------|--------------|------|
| 出题 | 真实用户 query 或 LLM 生成 | 人工根据文档标题构造 ✅ | 合理 |
| 候选池 | **Pooling 多系统结果** | 单个系统（FTS）搜 top-20 | ❌ 有偏见 |
| 标注 | 人工或 LLM 判 relevance | LLM (deepseek-v4-pro) 判 | ⚠️ 候选池有问题 |
| 指标 | Recall@K, MRR, nDCG | 待实现 | - |

**核心问题**：我们的候选池只来自关键词检索（FTS），这个池子本身就**漏掉了很多正确答案**。

---

## 改进建议

### 方案 A：Pooling 多系统（低依赖，稳妥）

```
对每道题:
  1. FTS 关键词检索 → top-20
  2. 向量语义检索         → top-20
  3. Hybrid 混合检索      → top-20
  4. 三路结果合并去重      → 候选池（约 30~45 个）
  5. LLM 逐条判 relevance
```

### 方案 B：纯 LLM 判断（当前做法改进版）

```
对每道题:
  1. Hybrid 检索 → top-30 候选（换掉纯 FTS）
  2. 加大 LLM 上下文 → 每个 chunk 给 800 字符
  3. temperature=0, deepseek-v4-pro
  4. 人工抽检 5~10 条
```

### 方案 C：RAGAS 端到端（自动化最高）

```
安装 ragas → 从 kb_chunks 自动生成<query, answer>对
→ 用 ragas 内置指标评估 5 组检索策略
→ 全自动，但需要对 ragas 做适配
```

---

## 推荐

**先走方案 A（Pooling）。** 理由：
- 不需要新依赖
- 候选池更完整，标注质量更高
- 你在面试时可以说"我用了 TREC 标准的 Pooling 方法构建测试集"

流程改动很小：把 LLM 标注脚本里的 `search_chunks()` 改成三路检索 → 合并去重 → 发给 LLM。
