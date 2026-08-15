# RAG v2 Chunker 快速可用 TODO

> 状态：待执行
> 创建：2026-08-10
> 目标：用最小改动消除 chunk 无法关联、正文静默丢失和 leaf 超限问题
> 依据：[文档清洗与层级切分工作记录](./RAG-v2-文档清洗与层级切分工作记录.md#12-chunker-快速可用优化范围2026-08-10)

## 1. 完成标准

本任务只交付一个可用的 Chunker MVP：

- 非空文档至少产生一个 leaf；
- 每个 leaf 都关联正确的 `doc_id` 和连续 `chunk_index`；
- 每个 leaf 的真实 `token_count <= 512`；
- 标题前正文、表格前后正文和表格数据不再静默丢失；
- 现有 Markdown pipeline 测试和新增 Chunker 测试通过；
- 使用固定 20 篇真实文档完成只读 baseline/candidate 对比；
- 不执行全量 rechunk 或 embedding。

完成本任务不代表已经得到最优语义切分，只代表最严重的数据完整性问题得到控制。

## 2. 修改范围

允许修改或新增：

```text
backend/ai/knowledge/chunker.py
backend/tests/test_kb_chunker.py
backend/scripts/audit_kb_chunker.py                 # 仅在确有必要时新增，只读
docs/ai/rag/samples/chunker-mvp/manifest.json       # 只保存元数据，不保存正文
docs/ai/rag/samples/chunker-mvp/baseline-report.json
docs/ai/rag/samples/chunker-mvp/candidate-report.json
docs/ai/rag/RAG-v2-chunker-TODO.md
docs/ai/rag/RAG-v2-文档清洗与层级切分工作记录.md
```

不要修改：

```text
backend/ai/knowledge/cleaner.py
backend/ai/knowledge/routes.py 中的 outline 规则
backend/ai/knowledge/embedder.py
backend/ai/knowledge/retriever.py
backend/ai/knowledge/reranker.py
数据库 schema
```

## 3. 已确认问题

以下问题已有本地最小复现，不需要再次争论是否存在：

| 编号 | 输入 | 当前结果 | 期望 |
|------|------|----------|------|
| C-01 | 499 个中文字符的短文档 | 1 个 898-token leaf，`doc_id=""` | 正确 doc_id，且所有 leaf ≤512 token |
| C-02 | 首标题前包含摘要的结构化文档 | 摘要未进入任何 leaf | 摘要进入文档级 preamble leaf |
| C-03 | 表格前后都有说明的长表格文档 | 只保留表格键值行 | 前说明、表格数据、后说明全部保留 |
| C-04 | 4000 个无标点字符的会议文档 | 产生 1200-token leaf | 继续切分到每个 leaf ≤512 token |
| C-05 | Markdown 下载后对短文档 rechunk | 按原 node_id 查不到 chunk | 现有 pipeline 测试通过 |

历史记录中的“302 篇覆盖率低于 20%”只作为排查入口。该数字可能受旧版本、父块重复和统计口径影响，执行前必须重新做只读统计，不能直接当作当前准确数量。

## 4. 编码前需要排查的内容

### 4.1 数据库只读基线

确认当前库中以下数量，禁止 UPDATE/DELETE：

```sql
-- 无法关联到文档的 leaf
SELECT COUNT(*)
FROM kb_chunks
WHERE depth = 1 AND (doc_id IS NULL OR doc_id = '');

-- 有 content 但没有关联 leaf 的文档
SELECT COUNT(*)
FROM kb_documents d
LEFT JOIN kb_chunks c
  ON c.doc_id = d.node_id AND c.depth = 1
WHERE d.content IS NOT NULL AND d.content <> ''
  AND c.id IS NULL;

-- 超过当前 leaf 硬上限的文档与 chunk 数量
SELECT COUNT(*) AS chunk_count, COUNT(DISTINCT doc_id) AS doc_count,
       MAX(token_count) AS max_tokens
FROM kb_chunks
WHERE depth = 1 AND token_count > 512;
```

另外只读抽取：

- `doc_id` 为空的 chunk 对应内容特征；
- 没有 leaf 的非空文档长度分布；
- `token_count > 512` 的文档类型和最大值；
- 历史低覆盖文档中仍然低覆盖的数量；
- 表格型文档是否普遍缺失首尾说明。

覆盖率只能用于筛选，不能单独作为正确性结论。父块重复、表头重复或格式转换都可能让字符比例失真，最终仍需检查具体内容是否被保留。

### 4.2 代码路径排查

执行 AI 修改前必须确认：

- `chunk_document()` 的所有提前返回位置；
- `_plain_leaf()` 是否可能接收超过 512 token 的内容；
- `_fixed_window()` 的无标点、单句、单行超限分支；
- `_chunk_meeting_v3()` 和 `_chunk_table_v3()` 是否绕过统一上限；
- `_build_sections()` 在首个 outline 行大于 1 时的覆盖范围；
- `_merge_tiny_leaves()` 是否会重新产生超限 leaf；
- routes v3 和 auto sync 是否直接使用 chunk 返回的 `doc_id/chunk_index`；
- parent 构建是否依赖修复前的 leaf 元数据。

## 5. 固定 20 篇真实样本

不再随机选 100 篇。建立一个小而明确的 20 篇 Chunker canary，正文不进入仓库，只保存 node、标题、hash、长度、分类和预期检查点。

| 分类 | 数量 | 选择条件 |
|------|-----:|----------|
| short | 4 | 100–499 字符；至少 2 篇中文密集，当前有 chunk 关联风险 |
| structured_preamble | 4 | 首个 outline entry 不在第 1 行，标题前有真实摘要或说明 |
| table | 6 | 纯表格 2、表格前后正文 2、多表格或超长行 2 |
| oversize | 3 | 无标点长段落、超长 JSON/配置、长代码块各 1 |
| healthy_control | 3 | 当前切分正常的普通正文、结构化文档、会议文档各 1 |

样本必须满足：

- 20 个不同 `node_id` 和不同 content hash；
- 实际内容满足分类条件，不能只根据标题推断；
- 至少 5 篇来自当前低覆盖或无 chunk 集合；
- 至少覆盖 3 个 workspace，避免单一来源格式偏差；
- manifest 不保存正文、数据库凭据或临时访问地址；
- 选定后固定，不因为 candidate 失败而换样本。

建议 manifest 字段：

```json
{
  "node_id": "...",
  "workspace_id": "...",
  "title": "...",
  "category": "table",
  "content_sha256": "...",
  "content_chars": 1234,
  "content_tokens": 567,
  "expected_markers": ["表前说明", "表后说明"]
}
```

`expected_markers` 只能保存短小的结构检查点，不能复制业务正文段落。

## 6. Baseline 需要记录什么

对当前 Chunker 运行 20 篇只读 baseline，每篇记录：

```text
node_id/category
source_chars/source_tokens
doc_type
leaf_count/parent_count
blank_doc_id_count
empty_leaf_count
max_leaf_tokens
source_lexical_recall
first_marker_preserved/last_marker_preserved
table_source_row_count/table_rows_preserved
deterministic
issues[]
```

指标定义：

- `source_lexical_recall`：source 中可检索词在所有 leaf 内容并集中的召回率，用于发现静默丢词；
- `first/last_marker_preserved`：确认前言、首段、尾部说明没有被策略跳过；
- `table_rows_preserved`：普通表格数据行必须在 leaf 中存在，不要求本轮理解合并单元格；
- `deterministic`：同一输入连续运行两次得到相同 leaf 内容、顺序和元数据；
- parent 不计入正文覆盖率，避免重复内容掩盖 leaf 丢失。

baseline 失败是预期现象，不得修改样本或指标让报告变绿。

## 7. 实现任务

### TODO-01：先补失败测试

新增 `backend/tests/test_kb_chunker.py`，把 C-01 至 C-04 固化成失败测试，并保留现有 pipeline 的 C-05。测试直接调用公开 `chunk_document()`，不要只测试私有函数。

### TODO-02：统一 leaf 收尾

调整 `chunk_document()`：

1. 短文档只选择单 leaf 策略，不在公共收尾前 return；
2. 所有策略完成后统一执行 leaf 硬上限处理；
3. 对超限 leaf 继续切分，并用真实 `count_tokens()` 反复验证；
4. 最后统一填写 `doc_id` 和连续 `chunk_index`；
5. `_merge_tiny_leaves()` 之后再次验证上限；
6. 非空输入没有 leaf 时使用保真 fixed-window 兜底。

不要分别给 short、meeting、table 编写三套超限算法。

### TODO-03：保留 outline 前言

当首个有效 outline entry 的行号大于 1 时，在 `_build_sections()` 前面增加 synthetic preamble section：

- 范围为文档第 1 行至首标题前一行；
- 空白 preamble 不生成 leaf；
- heading 可为空，section path 使用文档标题；
- 不改变后续真实 outline entry 的行号和层级。

### TODO-04：表格改为保真优先

快速版本停止使用“只抽取首张表格并丢弃非表格行”的做法：

- 整篇内容按现有行/窗口能力切分；
- 保留表格前后正文、多个表格、表头、分隔行和数据行；
- 正常表格行不从中间截断；
- 超长单行交给统一 leaf 上限兜底；
- 暂不实现复杂表格结构化。

若继续保留键值化表示，也必须证明原始正文和所有表格行都有对应 leaf；不得只返回压缩后的表格行。

### TODO-05：运行 candidate 对比

使用完全相同的 20 篇 manifest 生成 candidate report。报告必须由脚本直接输出，不手工修改 JSON，不连接写库。

逐篇人工查看所有 baseline/candidate 变化，重点检查：

- 原来缺失的前言和表格尾部是否恢复；
- 表格数据是否因为切分产生错行或丢列；
- 超长内容是否只是被拆分，没有被截断；
- section path 是否保持基本可读；
- healthy control 是否出现 chunk 数量暴涨或边界明显退化。

## 8. 验收门槛

单元测试：

```bash
cd management-system/backend
python3 -m unittest tests/test_kb_chunker.py
python3 -m unittest tests/test_kb_markdown_pipeline.py
python3 -m py_compile ai/knowledge/chunker.py
cd ..
git diff --check
```

20 篇 candidate 必须满足：

- 20/20 非空文档至少一个 leaf；
- blank `doc_id` 为 0；
- empty leaf 为 0；
- 20/20 最大 leaf token 不超过 512；
- 4/4 structured preamble 首段保留；
- 6/6 table 的前后检查点和数据行保留；
- 3/3 oversize 不丢首尾内容；
- 3/3 healthy control 无新增内容丢失；
- 20/20 deterministic；
- `source_lexical_recall` 最低值不低于 0.98，低于 1.0 的样本必须人工解释；
- 任一文档 leaf 数量超过 baseline 3 倍时人工检查，不能只因满足 512 上限就接受。

只要出现错误 doc_id、leaf 超限、正文首尾丢失或表格数据行丢失，即判定不通过。

## 9. 修复后需要排查的存量范围

candidate 通过后，只读生成受影响 node_id 清单：

1. 有 content 但没有关联 leaf 的文档；
2. 存在 `token_count > 512` leaf 的文档；
3. 当前 chunk 覆盖率低于 20% 的文档；
4. 表格型且首尾正文未进入 leaf 的文档；
5. 本次 20 篇 canary 中 baseline/candidate 不同的文档。

首轮只对清单内文档定向 rechunk。chunk 内容变化后，相应旧 vectors 必须删除并重新生成；这不等于全量重建。执行 rechunk/embed 必须另建任务并再次获得人工确认，本 TODO 不执行线上写操作。

## 10. 明确不做的优化

- 不调整 leaf/parent token 参数；
- 不引入 Markdown AST 或 LLM；
- 不按语义相似度合并段落；
- 不优化 outline 识别；
- 不重做父块聚合；
- 不实现复杂表头、合并单元格、单元格继承；
- 不加入 OCR、图片理解或代码语法树；
- 不修改召回、rerank 和上下文展开；
- 不全量 rechunk，不全量 embedding。

## 11. 执行报告

执行完成后更新工作记录，至少包含：

```text
修改文件
确认的根因
新增测试及结果
20 篇样本选择分布
baseline/candidate 指标
人工检查结论
受影响存量文档数量
建议定向 rechunk 的 node_id 清单位置
未解决问题
```

交付时不要只报告“测试通过”。必须说明是否仍存在内容丢失、超限 leaf 或无法关联的 chunk。
