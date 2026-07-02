# RAG 检索对照试验工作台

> A vs B 对照实验：基线 vs 基线+Cross-Encoder 重排

---

## 工作清单

### [x] 1. 标注测试集 ✅

**方法**: TREC Pooling（三路检索合并）+ LLM-as-Judge（deepseek-v4-pro）

**文件**: `test_queries.json`（26 条，135 个标注 chunk，0 空题）

**脚本**:
```bash
python -m ai.knowledge.rag_improve.step01_build_testset              # 全量标注
python -m ai.knowledge.rag_improve.step01_build_testset --retry-empty  # 只补标空题
python -m ai.knowledge.rag_improve.step02_auto_label                  # 自动预标注（备用）
```

**文档**: `docs/02-how-to-build-testset.md` — TREC Pooling + LLM-as-Judge 完整方法

---

### [x] 2. 建新向量表 + 安装模型 ✅

**pgvector 表**（已建）:
- `chunk_vectors` — bge-small 512d（当前生产用）
- `chunk_vectors_bgem3` — bge-m3 1024d（后续实验用）
- `chunk_vectors_large` — bge-large 1024d（后续实验用）

**已下载模型** (`local_models/BAAI/`):
- `bge-large-zh-v1.5` — 1.3GB ✅
- `bge-reranker-v2-m3` — 2.2GB ✅（当前实验用）
- `bge-m3` — 下载未完成，C/D 组实验前需重下

---

### [ ] 3. 批量编码存量 chunk → 新向量表

**文件**: `step06_encode_vectors.py`

A vs B 实验**不需要**这一步（直接用 `chunk_vectors`）。C/D/E 组实验前再跑。

---

### [x] 4. 实现检索策略 ✅

**文件**: `step03_strategies.py`

| 组 | 嵌入 | 检索 | 重排 | 状态 |
|----|-----|------|------|------|
| A | bge-small 512d | Hybrid RRF | 无 | ✅ |
| B（v1/v2） | bge-small 512d | Hybrid RRF | v2-m3 / 双路 | ✅ 已废弃 |
| **B（v3）** | bge-small 512d | Hybrid RRF top-20 | **bge-reranker-base** | **✅ 推荐** |

---

### [x] 5. 实现评估指标 ✅

**文件**: `step04_metrics.py`

- Recall@5 — 前 5 条命中正确答案的比例
- MRR — 第一个正确答案排名的倒数均值
- nDCG@5 — 归一化折损累积增益

---

### [x] 6. 跑实验 + 输出报告 ✅

| 版本 | 策略 | 模型 | Recall@5 | 本地 | 服务器 (i7) |
|------|------|------|----------|------|------------|
| v1 | 单路 Hybrid | v2-m3 (2.2GB) | 63.3% | 38s | ~2-3s |
| v2 | 双路召回 | v2-m3 (2.2GB) | 60.0% | 40s | 证伪 |
| **v3** | **单路 Hybrid** | **base (280MB)** | **59.6%** | 5s | **~1s** ✅ |

**部署**：服务器 CPU 跑 base ~1s/query，`reranker_model="v2-m3"` 可切高精度模式。

详见 [`docs/01-RAG检索优化-调研与实验方案.md`](./docs/01-RAG检索优化-调研与实验方案.md)

---

## 目录结构

```
rag_improve/
├── README.md                        ← 你正在看的
├── test_queries.json                ← 标注测试集 (26 题, 135 chunks)
│
├── step01_build_testset.py          ← 主标注流水线 (TREC Pooling + LLM)
├── step02_auto_label.py             ← 自动预标注 (source_doc 匹配备用)
├── step03_strategies.py             ← A/B 检索策略定义
├── step04_metrics.py                ← Recall@K / MRR / nDCG@K
├── step05_runner.py                 ← 对照实验运行器
├── step06_encode_vectors.py         ← 批量编码 bge-large/bge-m3 (后续用)
├── step07_annotate.py               ← 交互式标注工具 (备用)
│
└── docs/
    ├── 01-RAG检索优化-调研与实验方案.md   ← 主文档：调研 + 实验方案
    ├── 02-how-to-build-testset.md       ← 测试集构建方法论
    ├── 03-step1-annotation.md           ← Step1 标注说明
    ├── 04-10-RAG检索调研与优化方案.md     ← 全景调研 (leagcy)
    └── 05-13-rag-retrieval-benchmark.md  ← 5组实验设计 (legacy)
```
