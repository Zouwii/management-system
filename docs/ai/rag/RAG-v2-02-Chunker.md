# RAG v2：Chunker 与 Leaf 工作记录

> 状态：Parent 链路代码已修复但未启用，Chunker 优化暂停 | 更新：2026-08-18
> 样本目录：服务器 `/home/jz/zhr/markdown/`  
> 文档索引：[RAG v2 文档索引](./RAG-v2-00-文档索引.md)
> 关联设计：[RAG v2：Markdown 与图片多模态检索设计](./RAG-v2-04-多模态扩展.md)
> Cleaner 专项审计：[RAG v2：Cleaner 数据驱动迭代](./RAG-v2-01-Cleaner.md)

## 1. 概要

当前已完成的工作链路：

```text
服务器 markdown 文件 (5426 篇, 55GB)
    → cleaner 清洗 → kb_documents.content (4527 篇)
    → outline 提取 → kb_documents.outline
    → chunker 切分 → kb_chunks (32915 叶子 + 9169 父块 = 42084)
    → embedder 向量化 → pgvector (31310 条)
```

## 2. 数据全景（2026-08-05 实测）

### 2.1 导入结果

| 指标 | 数量 | 占比 |
|------|------|------|
| kb_documents 总数 | 6722 | 100% |
| 有 markdown 文件 | 5425 | 80.7% |
| 成功匹配并导入 | 4345 | 64.6% |
| 未匹配（无 kb_document 条目） | 1080 | 16.1% |
| 无 markdown 文件的文档 | 1297 | 19.3% |

1080 篇未匹配的主要是 TEL/TEL5、比力、茂佳、金海通等工作区的文档，这些工作区不在当前 kb_documents 同步列表中。

### 2.2 内容规模

| 文档长度 | 篇数 | 占比 | 平均字符数 |
|----------|------|------|-----------|
| <500 字 | 928 | 22.9% | 249 |
| 0.5K-2K | 1579 | 38.9% | 1,090 |
| 2K-5K | 876 | 21.6% | 3,161 |
| 5K-10K | 389 | 9.6% | 7,005 |
| 10K-30K | 253 | 6.2% | 15,183 |
| 30K-80K | 30 | 0.7% | 48,357 |
| >80K | 1 | 0.02% | 105,602 |
| **合计** | **4056** | 100% | — |

922 篇（23%）是短文档（<2K），可直接用一个 chunk 覆盖，不需要分层切分。

### 2.3 Outline 提取结果

4056 篇有内容的文档中，3971 篇成功提取出 outline。按首个标题来源分布：

| 来源 | 篇数 | 占比 | 说明 |
|------|------|------|------|
| `markdown` | 2781 | 68.6% | 标准 `#` 标题，层级正确 |
| `implicit_digit` | 336 | 8.3% | `1.` `1.1` 数字编号，新增识别 |
| `implicit_bold` | 255 | 6.3% | `**粗体标题**` 作为标题 |
| `implicit` | 78 | 1.9% | `一、` `二、` 中文编号 |
| `implicit_letter` | 1 | 0.02% | `a)` 字母编号 |
| `implicit_fallback` | 520 | 12.8% | 无结构，首行作为标题 |
| `empty` | 85 | 2.1% | 纯表格或空文档 |

**有结构的分级目录**（markdown + digit + bold + cn + letter）：**3451 篇（85.1%）**。
剩余 605 篇无结构文档需要后续用 LLM 生成标题或接受回退。

### 2.4 数据库状态

```
kb_documents: 6722 行
  content  有内容: 4056  →  MEDIUMTEXT，清洗后 Markdown
  outline  有内容: 3971  →  MEDIUMTEXT，JSON 数组 [{level, title, line, path, source}]
  两者均为空:       2666  →  无 markdown 或未导入

kb_chunks:  42084 行 → 32915 叶子 + 9169 父块（全量完成）

kb_nodes:   0 行 → 目录树同步未执行（不在本次范围）
```

## 3. Outline 提取设计

### 3.1 提取规则

`extract_outline_v2()` 从清洗后 Markdown 提取标题结构，输出扁平数组：

```json
[
  {“level”: 2, “title”: “硬件准备”, “line”: 15, “path”: “Setup步骤 > 硬件准备”, “source”: “markdown”},
  {“level”: 1, “title”: “地图更新方式”, “line”: 1, “path”: “地图更新方式”, “source”: “implicit_digit”}
]
```

识别顺序（优先级从高到低）：

1. **Markdown 标题**：`#` ~ `######`，计算层级与 `path`
2. **中文编号**：`一、` `一.` `一)` 等
3. **数字编号**：`1.` `1.1` `1.1.1` `1、` `(1)` 等，层级由 `.` 数量推断
4. **字母编号**：`a)` `A.` 等，固定 L2
5. **粗体独立行**：`**标题**` 独占一行，且之前无标题
6. **回退**：取第一个非表格行作为标题

标题清洗：去掉 `**` 包裹、末尾残余数字。

### 3.2 实际分布

见 §2.3。85.1% 文档有结构化分级目录。

### 3.3 实现

脚本：`backend/scripts/fix_outline.py`（189 行）
调用：`extract_outline_v2(content) → List[dict]`
写入：`kb_documents.outline`（JSON 数组）

---

## 4. Chunker 设计（已实现）

### 4.1 现有 chunker 的问题

当前 `chunker.py`（505 行）存在以下不足：

| 问题 | 现状 | 设计文档要求 |
|------|------|-------------|
| chunk 太大 | 500-1200 token | 叶子 220-420 token，硬上限 512 |
| 无父子结构 | 扁平 chunk | “小块召回，大块生成” |
| 章节路径弱 | 重新解析 `##` `###` | 直接用 pre-computed `outline` |
| 元数据粗糙 | `[来源: title] [章节: heading]` | `section_path: Setup > 2.3 > 嵌入式软件更新` |
| 表格原子性 | 行可能跨 chunk | 一行不能跨 chunk |
| 代码块 | 无特殊保护 | 整块保护 |

### 4.2 预估 chunk 总量

基于 4056 篇文档的长度分布，不同 chunk 大小方案的总量估算：

| 方案 | leaf 大小 | chunk 总量 | 父块 | 合计 |
|------|----------|-----------|------|------|
| 现状 | 800-1200 | ~14,000 | 0 | ~14,000 |
| 折中 | 400-600 | ~20,000 | 0 | ~20,000 |
| 设计文档 | 220-420 | ~26,000 | ~8,000 | ~34,000 |

分析：928 篇（23%）文档 <500 字，一个 chunk 足够，不需要分父子。长文档（>3K）才真正受益于父子结构。

### 4.3 建议分层策略

```
短文档 (<500 字)   → 1 个 chunk，不分子父
中长文档 (500-3K)  → 220-420 leaf，无父块
长文档 (>3K)       → 220-420 leaf + 按 section 聚合的父块
```

预估总量：~22,000 叶子 + ~3,000 父块 = **~25,000 chunk**。

### 4.4 `kb_chunks` 表结构

在现有表基础扩展（非新建）：

```sql
ALTER TABLE kb_chunks ADD COLUMN parent_id INT DEFAULT NULL;
ALTER TABLE kb_chunks ADD COLUMN depth TINYINT DEFAULT 0;       -- 0=父块, 1=叶子
ALTER TABLE kb_chunks ADD COLUMN chunk_type VARCHAR(20) DEFAULT 'paragraph';
ALTER TABLE kb_chunks ADD COLUMN section_path VARCHAR(1024) DEFAULT '';
```

### 4.5 切块流程

```
content + outline
    → classify_document() (保留现有四分类)
    → outline 驱动切分（非重新解析 ##）
        → 定位章节边界（按 outline.line 二分查找）
        → 块内保护：代码块、表格行、列表项不可切断
        → 注入 section_path 到每个 chunk
    → 父块聚合（仅长文档）
        → 同一 section_path 下叶子合并为父块
    → 写入 kb_chunks
```

### 4.6 复用 vs 重写

| 组件 | 决策 | 原因 |
|------|------|------|
| `classify_document()` | 保留 | 四分类逻辑仍适用 |
| `chunk_structured()` | 重写 | 改为 outline 驱动 |
| `chunk_table()` | 改造 | 缩小上限 + 行原子性 |
| `chunk_meeting()` | 改造 | 缩小上限 |
| `chunk_text()` | 保留 | 只改参数 |
| `count_tokens()` | 保留 | 不变 |

### 4.7 检索展开策略（后续实现）

```
查询 → 叶子 chunk 检索 (220-420 token, 不会被 embedding 截断)
     → 命中后展开:
         → 父 chunk (同 section_path, 600-1200 token)
         → 相邻叶子 (同 section_path, ±1)
     → 去重后组装 LLM 上下文 (6000-8000 token 预算)
```

---

## 5. 实施进度

- [x] 确认清洗后的 Markdown 作为 `kb_documents.content` 原文
- [x] 从服务器选取五种典型 Markdown 样本
- [x] 确定清洗规则 v1 和 `CleanResult` 接口
- [x] 实现 cleaner（`cleaner.py`，364 行，9 个回归测试）
- [x] 15 篇样本验证通过（5 首样 + 10 补充）
- [x] 批量清洗 5425 篇 markdown → `kb_documents.content`（4345 篇成功）
- [x] `raw_json` 改名为 `outline`
- [x] 实现 outline 提取（`extract_outline_v2()`）
- [x] 全量提取 4056 篇 outline → `kb_documents.outline`（3971 篇成功）
- [x] 扩展 `kb_chunks` 字段（parent_id, depth, chunk_type, section_path）
- [x] 实现 v3 chunker（outline 驱动，叶子+父块）
- [x] embedder 接入（depth=1 只 embed 叶子，首次加载慢见 §7）
- [x] 全量索引完成（4527 篇文档 → 42084 chunks → 31310 vectors）
- [x] 路径链路修复（ws_id → 中文名映射，命中率 0% → 65%）
- [x] search_v3 集成 reranker（代码就绪，等 CPU 不降频启用）
- [x] `/v3/sync` 全链路打通
- [ ] 3 篇超大文档（ALTER TABLE kb_chunks.content → MEDIUMTEXT）
- [ ] 302 篇 chunk 覆盖率 <20%（chunker 表格处理待修）
- [ ] 2252 篇 pending 需 MCP 下载
- [ ] 998 磁盘孤儿文件无 kb_node 匹配

## 6. v3 Chunker 实测记录（2026-08-05）

### 6.1 实现方案

重写为 `chunker.py`（497 行），基于 pre-computed `outline` JSON 驱动切分：

```
content + outline
  → 短文档 (<500 chars) → 1 个叶子 chunk
  → 中长文档 (500-3K)  → 220-420 token 叶子，无父块
  → 长文档 (>3K)       → 220-420 token 叶子 + 按 section_path 聚合的父块
```

参数：LEAF_TARGET=320, LEAF_MIN=150, LEAF_MAX=512, PARENT_TARGET=800, PARENT_MAX=1200。

原子保护：代码块、表格行、列表项不会被切断。

### 6.2 小工作区实测（MJ0pDSwlOEkMqQ0E，28 篇）

| 文档大小 | 篇数 | 叶子 | 父块 | 说明 |
|----------|------|------|------|------|
| <500 字 | 13 | 1/篇 | 0 | 项目概要，单 chunk 够用 |
| 0.5K-3K | 9 | 2-5/篇 | 0 | 需求追踪表、检查单 |
| 3K-20K | 6 | 4-30/篇 | 配套 | 例会记录、物料库 |

**汇总：28 篇 → 103 叶子 + 29 父块（3.7 叶子/篇）**

叶子 token 分布：min=8, max=457, avg=251, median=284。超过 512 的 = 0，低于 50 的 = 3（纯标题块）。

### 6.3 全量估算

基于 4056 篇按上述比率外推：

| 方案 | 叶子目标 | 预估叶子 | 预估父块 | **合计** |
|------|----------|---------|---------|---------|
| A（当前） | 220-420 token | ~15,000 | ~4,000 | **~19,000** |
| B | 400-600 token | ~9,000 | ~2,500 | **~11,500** |
| C（旧版） | 800-1200 token | ~14,000 | 0 | **~14,000** |

### 6.4 遇到的坑

**坑 1：outline 过度切分。** Roadmap 类文档（表格型），outline 提取把每一行都识别为"标题"。例如「2025年导航组Roadmap.adoc」（3375 字）产生了 135 个 outline entry，对应 135 个单行 section。切分后每个叶子只有 3-24 token。

→ 解决：增加 `_merge_tiny_leaves()` 后处理，相邻极小叶子自动合并到 LEAF_TARGET。135 叶子 → 合并为 11 叶子 + 8 父块，avg=290 token。

**坑 2：超大单行吞入。** 某些文档（如 50 句重复拼接的段落）产生 1000+ token 的单行。`_chunk_section_leaf` 的 `buf_tokens < LEAF_MIN` 守卫过松，0 + 1000 < 150 → True，整行吞入。

→ 解决：对大行（`lt > LEAF_MAX`）先做 `_fixed_window` 切分再入 buffer。

**坑 3：部分文档 outline 过于简单。** 会议纪要类（3703 token）只有 3 个 `##` 标题，每个 section 内是整张 markdown 表格。3 个 section 各产一个叶子后，`_merge_tiny_leaves` 合并成 1 个（127 token）。

→ 待评估：这是 outline 提取质量问题，不是 chunker 的 bug。这类文档用 text chunker（`_fixed_window`）可能更合适。

## 7. Embedder 问题：CPU 模型加载延迟

### 7.1 现象

服务器 172.19.3.79 **无 GPU**（`nvidia-smi` 超时无输出），`BAAI/bge-small-zh-v1.5` 模型在 CPU 上通过 `SentenceTransformer` 首次加载耗时 **3 分钟以上**（180s timeout 仍未完成）。

### 7.2 影响

- 首次 embed 调用需要等待 3-5 分钟加载模型
- 加载后模型常驻内存（~400MB），后续调用正常（~100ms/chunk）
- 每次进程重启需重新加载
- 4056 篇文档 × 3.7 chunk/篇 ≈ 15,000 叶子，embed 耗时约 15000 × 0.1s = 25 分钟（模型加载后）

### 7.3 选项

| 方案 | 优点 | 缺点 |
|------|------|------|
| 接受首次延迟 | 不改代码 | 用户体感差 |
| app 启动时预加载 | 首次调用无感 | 启动变慢 3-5min |
| 换 GPU 服务器 | 加载 <10s | 需要硬件 |
| 换更小模型 | 加载快 | 精度下降 |

## 8. 精度 vs 效率核心矛盾

### 8.1 叶子大小权衡

| 叶子大小 | chunk 总量 | embedding 精度 | 上下文质量 |
|----------|-----------|---------------|-----------|
| 小 (220-420) | ~19,000 | **高** — 精准匹配段落 | 中等 — 需展开父块 |
| 中 (400-600) | ~11,500 | 中 — 可能含噪音 | **高** — 自包含 |
| 大 (800-1200) | ~14,000 | **低** — embedding 截断 | 高 — 但粒度粗 |

### 8.2 待决策

当前方案 A（220-420）的 19,000 个 chunk 是否可接受？

- **存储**：19K × 512 维 × 4 bytes = 39 MB（可忽略）
- **embed 耗时**：模型加载 3-5min + 编码 25min = 首轮 ~30min
- **检索召回**：小块更精准，但需配合父块展开才能保证上下文完整

方案 B（400-600）折中：chunk 减半到 ~11,500，精度损失待 canary 测试评估。

**下一步**：需要跑一个 canary 测试集来量化不同叶子大小对 Recall@5 的影响。

## 9. 相关脚本

| 脚本 | 路径 | 用途 |
|------|------|------|
| cleaner 库 | `backend/ai/knowledge/cleaner.py` | `clean_markdown()` 清洗函数 |
| chunker v3 | `backend/ai/knowledge/chunker.py` | outline 驱动父子块切分（497 行） |
| embedder | `backend/ai/knowledge/embedder.py` | SentenceTransformer → pgvector |
| retriever | `backend/ai/knowledge/retriever.py` | keyword/vector/hybrid/rerank 检索 |
| reranker | `backend/ai/knowledge/reranker.py` | bge-reranker-base 交叉编码 |
| routes v3 | `backend/ai/knowledge/routes_v3.py` | /v3/sync, /v3/download, /v3/import, /v3/index, /v3/status |
| models | `backend/ai/knowledge/models.py` | KbDocument / KbNode / KbChunk ORM |
| schema | `backend/scripts/migrate_kb_storage.sql` | kb_chunks 扩展 + pgvector 迁移 |

---

## 10. 最终状态（2026-08-05 全量完成）

### 10.1 数据库

| 表 | 记录数 | 说明 |
|-----|--------|------|
| kb_documents | 6779 | 4836 success + 1943 pending（含产品信息门户 246 篇非文本格式） |
| kb_chunks | 46853 | 35698 leaf + 11155 parent |
| chunk_vectors | ~35000 | 本次新增产品信息门户 ~3600 条（embed 进行中） |

### 10.2 链路修复记录

| 问题 | 修复 | 结果 |
|------|------|------|
| breadcrumb 路径 0% 命中 | `_build_md_path()` 查 `kb_workspaces.json` 做 ws_id→中文名映射 | 命中率 → 65% |
| 磁盘有文件但 DB 无记录 | 文件名 fallback 搜索 + 补建 kb_documents | +57 新建 +413 导入 |
| 超大单行 JSON (28K token) | `_force_split_long()` 兜底 | 仍有 3 篇失败 |
| outline 过度切分 | `_merge_tiny_leaves()` 合并 | 135→11 chunk |
| CPU 模型加载 3-5min | embedder 加 `device="cpu"` | 加载 4.6s |
| reranker 后台加载卡死 | 恢复同步加载 | 待 CPU 不降频后启用 |
| 产品信息门户 556 篇未下载 | MCP 批量下载 + v3 import/index | 310 篇入库，246 篇非文本跳过 |
| 冗余脚本 | 删除 4 个旧脚本 + v2 模块 | 保留 routes_v3/chunker/cleaner/embedder/retriever/reranker |

### 10.3 接口状态

| 端点 | 方法 | 状态 |
|------|------|------|
| `/v3/sync` | POST | ✅ 全步骤（meta/download/import/index） |
| `/v3/download` | POST | ✅ MCP 网关正常，支持 `parent_dir` |
| `/v3/import` | POST | ✅ clean + outline → kb_documents |
| `/v3/index` | POST | ✅ chunk + embed |
| `/v3/search` | POST | ✅ keyword+vector RRF，reranker 待启用 |
| `/v3/status` | GET | ✅ |

> ⚠️ 周一自动 sync（`kb_incremental_sync`）使用旧流程：MCP 下载原始 markdown → 直接标记 success，跳过 v3 的 clean + outline。因此 auto sync 产出的文档需手动跑 v3 import+index。`KB_AUTO_CHUNK_EMBED_ENABLED` 默认关闭。

### 10.4 已知问题

#### 10.4.1 Chunk 覆盖率不足（302 篇文档）

137 篇覆盖率为 0-5%，165 篇为 5-20%。共同特征：大篇幅 adoc/markdown 混合表格文档，cleaner 保留原始表格标记后 chunker 无法正确处理，造成 99% 内容丢失。

典型案例：60K 字符文档仅产出 600 token 的 chunk。

> 根因：outline 过度细粒度 + `_chunk_section_leaf` 原子表格块过大时 `_fixed_window` 分句失败。待修。

#### 10.4.2 Chunk 超 TEXT 限制（3 篇）

| 文档 | 原因 |
|------|------|
| `jzrouter-core-la库本体端使用方法.adoc` | chunk content 超 MySQL TEXT 65KB |
| `人形机器人OMNI300协议文档-V1.1.adoc` | 同上 |
| `（某超大 JSON 文档）` | 28K token 代码块未切开 |

> 修复：`ALTER TABLE kb_chunks MODIFY content MEDIUMTEXT`（16MB）。

#### 10.4.3 2252 篇 pending 需 MCP 下载

MCP 服务未运行，磁盘无对应 .md 文件。含产品信息门户（OQ0xySKEGYKEG48B）556 篇。

#### 10.4.4 998 磁盘孤儿文件无 kb_node

磁盘有文件但 kb_nodes 无匹配条目。多为 MCP 下载 .adoc 拆分为子目录/子 .md 的场景（如 `PRD.adoc → PRD/子章节.md`）。当前策略：暂不处理。

#### 10.4.5 Reranker 待启用

bge-reranker-base (3.2GB) 模型已部署，但服务器 CPU 限频至 54%，模型加载过慢。待 CPU 频率恢复后启用。

---

## 11. Outline 现状与暂不重建决策（2026-08-10）

### 11.1 当前判断

现有 `extract_outline_v2()` 已覆盖大部分普通文档类型：标准 Markdown 标题、中文编号、数字编号、字母编号、首个粗体标题和无结构文档首行回退。历史统计中，4056 篇有内容文档有 3971 篇生成 outline，覆盖率约 97.9%；其中 3451 篇具有明确的结构化层级，占 85.1%。

本轮 Cleaner 修复对 outline 的直接影响集中在少量整篇转义文档、标题内相邻 span，以及无标题文档首行的图片/文档链接。影响面不足以支持立即全量重建。

**决策：当前不重建存量 outline。** 保留现有 outline，不单独更新数据库，也不触发 chunks 或 vectors 重建。新导入文档继续按现有 `clean → outline` 链路生成。

### 11.2 已知但暂缓的问题

| 问题 | 当前影响 | 后续处理 |
|------|----------|----------|
| fenced code 内的 `#` 或数字行可能被识别成标题 | 少量代码密集文档产生伪目录 | 优先补“跳过代码块”规则 |
| `_clean_title_v3()` 删除标题末尾数字 | `Bit2`、年份、版本号等可能失真 | 优先取消无上下文的末尾数字删除 |
| 操作步骤可能被当成数字标题 | 部分教程类文档 outline 偏细 | 出现检索 Bad Case 后增加上下文约束 |
| 纯表格文档 outline 为空 | 85 篇空 outline 中包含纯表格或空文档 | 必要时生成单一文档根节点 |
| 后续粗体独立行不会继续成为标题 | 混合 Markdown/粗体结构可能漏章节 | 按样本验证后再扩展 |
| Roadmap 等文档 outline 过度切分 | 极端案例可产生上百个 entry | 继续由 chunker 合并兜底，后续增加标题密度降级 |

短期只考虑两个高收益修复：跳过 fenced code 内伪标题、保留标题末尾数字。其余问题按真实检索 Bad Case 数据驱动迭代，不重写 outline 提取器。

### 11.3 原 100 篇样本带来的经验

原 100 篇主要用于 Cleaner 审计，不是严格的 outline 评测集。样本中过短文档较多，长结构、整篇转义和真实相邻 span 覆盖不足，因此不能用来证明 outline 精度。

仍可保留以下经验：

- 样本分类必须校验文档确实包含目标结构，不能只依赖人工标签；
- 代码、表格、编号列表、整篇转义和无标题 fallback 应分别评价；
- 不能只统计 outline 是否非空，还要检查 entry 数量、来源、层级、标题密度和标题文本保真；
- 整篇转义会造成标题缺失，文档链接误判可能影响无标题文档的 fallback 标题；
- 普通文档覆盖已经足够，后续应优先收集失败样本，而不是重复扩大随机样本数量。

### 11.4 重新评估与重建触发条件

满足以下任一条件时再启动 outline 专项修复和存量重建评估：

1. 出现一批可复现的目录错误或检索 Bad Case；
2. 完成代码块伪标题和末尾数字修复；
3. 决定对存量文档重新执行 Cleaner；
4. outline 只读 old/new diff 表明变化范围足够大。

届时先对存量 content 只读计算新 outline 并比较差异，只更新实际变化的文档；若变化面很大，再考虑全量重建。单独更新 outline 不会同步改变已有 chunk 的章节路径，因此任何面向检索效果的重建需另行评估 chunk 一致性。

---

## 12. Chunker 快速可用优化范围（2026-08-10）

本节保留当时的快速修复范围；执行方案和最终结果已归档在 12.6～12.8，原临时 TODO 文档于 2026-08-18 完成清理。

### 12.1 目标与边界

本轮不追求通用 Markdown AST、语义切分、最优 chunk 参数或复杂表格理解，只修复会导致文档无法关联、正文静默丢失和单个 leaf 明显超限的问题。保持现有 `LEAF_TARGET=320`、`LEAF_MAX=512`、父子块结构和 document classification 基本不变。

### 12.2 已确认的硬问题

| 问题 | 代码位置 | 本地最小复现结果 | 影响 |
|------|----------|------------------|------|
| 短文档提前返回，没有填充 `doc_id` | `chunk_document()` 的 `<500 chars` 分支 | 499 个中文字符生成 1 个 leaf，`doc_id=""` | chunk 无法与原文档关联；现有 SQLite 流水线测试因此失败 |
| 短文档绕过 token 上限 | 同一提前返回分支 | 499 个中文字符生成 898-token leaf | embedding 可能截断，违反 512-token 硬上限 |
| 首个 outline 前的正文被丢弃 | `_build_sections()` | 标题前“前言内容”没有进入任何 leaf | 结构化文档前言、摘要或说明静默丢失 |
| 表格策略只提取表格行 | `_chunk_table_v3()` | 1696 字符表格文档的“表前说明”和“表后说明”均丢失 | 与已记录的低 chunk 覆盖率问题一致 |
| 部分策略仍能输出超长 leaf | meeting/table/超长句分支 | 4000 个无标点 ASCII 字符生成 1200-token leaf | 超过 leaf 上限，可能触发截断或字段风险 |

当前没有独立的 chunker 单元测试。`tests.test_kb_markdown_pipeline` 中已有一条短文档持久化测试会失败：rechunk 后按原 `node_id` 查不到 chunk，直接证明空 `doc_id` 是现存故障。

### 12.3 最小修复清单

#### P0-1：统一完成 leaf 元数据和硬上限检查

- 取消短文档在公共收尾逻辑之前直接返回；
- 所有策略生成 leaf 后统一填写 `doc_id`、`chunk_index`；
- 增加最终 leaf 校验：任何 `token_count > LEAF_MAX` 的 leaf 必须继续拆分；
- 拆分后使用真实 `count_tokens()` 复核，不能只依赖固定字符数估算；
- 保证任何非空文档至少生成一个 leaf。

这一处统一兜底即可覆盖短文档、无标点会议段落、超长表格行和超长 JSON，不为每种文档分别增加复杂规则。

#### P0-2：保证结构化文档前言不丢失

当第一个 outline entry 不在第 1 行时，`_build_sections()` 增加一个从第 1 行到首标题前的 synthetic preamble section。其 `section_path` 使用文档标题，后续真实章节逻辑保持不变。

#### P0-3：表格先采用保真切分

当前 `_chunk_table_v3()` 会把整篇内容压缩成首张表格的键值行，并跳过所有非表格正文。快速可用版本不继续扩展复杂表格解析，改为：

- 保留表格前后正文、标题和多个表格的原始可见文本；
- 使用现有行/窗口切分能力按 512-token 上限分组；
- 不拆断单个正常表格行；超长单行仍交给统一硬上限兜底；
- 暂不实现合并单元格、父级单元格向下填充和多层表头语义。

优先保证“内容不丢且可检索”，表头重复注入等精细优化等真实检索 Bad Case 出现后再做。

#### P0-4：补最小回归测试

新增独立 chunker 测试，至少覆盖：

1. 短文档 leaf 的 `doc_id` 和 `chunk_index` 正确；
2. 499 个中文字符不会产生超过 512 token 的 leaf；
3. 结构化文档首标题前正文被保留；
4. 表格前说明、表格行和表格后说明全部被保留；
5. 无标点超长段落的每个 leaf 均不超过 512 token；
6. 空文档仍返回空 leaf；
7. 现有 `test_kb_markdown_pipeline` 全部通过。

### 12.4 暂不处理

- 不调整 320/512/800/1200 token 参数；
- 不重写 document classification；
- 不做 Markdown AST 或 LLM 语义切分；
- 不优化父块聚合和 parent-child 关系；
- 不处理 outline 的伪标题和过度切分；
- 不实现复杂表格表头、合并单元格和单元格继承；
- 不修改 embedding、retriever 或 reranker；
- 不立即全量重建 chunks/vectors。

### 12.5 验收与存量处理

代码验收只看四项硬指标：

- 非空文档生成 leaf，且 leaf 能关联到正确 `doc_id`；
- 所有 leaf `token_count <= 512`；
- 标题前正文和表格前后正文不再静默丢失；
- 新增 chunker 测试及现有 Markdown pipeline 测试全部通过。

修复完成后先只读统计存量中的无关联 chunk、无 chunk 文档、`token_count > 512` 文档和 chunk 覆盖率低于 20% 的文档。首轮仅对这些受影响文档定向 rechunk；只有受影响范围接近全量时，才重新评估全量 chunks/vectors 重建。

### 12.6 本次直接执行结果（2026-08-10）

- 修改文件：`backend/ai/knowledge/chunker.py`、`backend/tests/test_kb_chunker.py`。
- 根因修复：取消短文档提前返回；统一在策略、tiny-leaf 合并之后按真实 `count_tokens()` 执行 512-token 硬上限；outline 首标题前增加 synthetic preamble；表格改为保留原始整篇行内容。
- 测试结果：`python3 -m unittest tests/test_kb_chunker.py`（4/4 通过）；`python3 -m unittest tests/test_kb_markdown_pipeline.py`（14/14 通过）；`python3 -m py_compile ai/knowledge/chunker.py` 和 `git diff --check` 通过。
- 本地 C-01～C-04 均确认：非空文档有 leaf、`doc_id` 正确、索引连续、leaf 不超过 512 token，前言/表格首尾/无标点正文保留。
- 已通过 `172.19.3.79` 只读连接固定 20 篇 canary（4 short、4 structured_preamble、6 table、3 oversize、3 healthy_control），覆盖 4 个 workspace，4 篇当前无 leaf。元数据见 `docs/ai/rag/samples/chunker-mvp/manifest.json`。
- 服务器 baseline：空 `doc_id` leaf 2663；有正文但无 leaf 文档 1048；超 512 token leaf 564，涉及 298 篇文档；最大 leaf 12048 token。详情见 `baseline-report.json`。
- candidate 已通过 SSH 只读管道读取同一 20 篇正文，并在本地候选代码上逐篇比较：20/20 有 leaf，blank `doc_id` 0，empty leaf 0，最大 512 token，首尾/表格 marker 20/20 保留，deterministic 20/20，最低 lexical recall 0.993405。详情见 `docs/ai/rag/samples/chunker-mvp/candidate-report.json`。
- 本次没有复制代码、修改服务器文件、数据库写入、rechunk 或 embedding；baseline 中暴露的存量问题仍需另建任务定向处理。

### 12.7 服务器存量修复 dry-run（2026-08-11）

- 服务器实际只读清单：A 类 1048 篇、B 类 297 篇、C 类 canary 20 篇，去重并集 1360 篇；空 `doc_id` leaf 2663 个单独保留为孤儿清单，不猜测归属。
- 服务器没有 git commit；候选 Chunker 仅临时放在 `/tmp`，SHA-256：`2bdc73257d74dadd86dd07b955729fe99a7484af59ff2a1185c6f48a0f516418`。
- 使用服务器真实 `content` 和 `outline` 对 1360 篇执行只读 dry-run：1360/1360 有 leaf，错误 0，错误 `doc_id` 0，断序索引 0，超 512 token leaf 0，最大新 leaf 512 token。
- 现有服务器 `rechunk_and_embed.py` 会全局处理、每 50 篇提交；`auto_sync._rechunk_documents()` 虽支持 doc_id 列表，但 20 篇共用一个事务，且服务器当前仍是旧 Chunker。因此未直接调用写库入口。
- 下一步必须先备份数据库、正式部署候选 Chunker，并补齐/确认按文档单独事务和定向 vector 删除/重建；在获得人工确认前不执行任何写库操作。

### 12.8 服务器定向存量修复结果（2026-08-12）

- 已备份：`/home/jz/zhr/backups/rag-v2-chunker-20260811-173510/kb_storage.sql`（149M，SHA-256 `83ebdd73ad364af6014db34b17a9feb556980c3e2a9664c095db92121796330b`）；`kb_vectors.dump`（92M，SHA-256 `ca77d0ac57e307bcffecf8d528410259c929d8ffedf6bda1a73b08a848a50f90`）。
- 已部署候选 Chunker，SHA-256 `2bdc73257d74dadd86dd07b955729fe99a7484af59ff2a1185c6f48a0f516418`；旧版本已保存为同一备份目录下的 `chunker.py.before`。
- 20 篇 canary 首批修复 20/20 成功；随后按单篇事务、每批最多 100 篇完成 A/B/C 并集定向修复。每篇均先删除其旧 vectors，再替换 chunks，提交后为新 chunks 生成 vectors；单篇失败会回滚且未出现失败项。
- 最终全库只读验收：4749 篇非空文档全部有 leaf；有正文无 leaf 为 0；有效 `doc_id` 的超限 leaf 文档为 0；有效文档对应 chunks 覆盖 4749 篇；非空 `doc_id` 孤儿为 0。
- 仍保留 2663 个空 `doc_id` 孤儿 chunk，未猜测归属、未删除；其中 103 个仍超过 512 token，均属于这些孤儿。孤儿处理需另行确认删除及检索引用影响。
- 最终数据库统计：`kb_chunks` 48137，`chunk_vectors` 39356。vectors 少于 chunks 的差异包含未纳入本次清单的历史块/父块状态，后续如需全量 vector 一致性需另建任务，不在本次定向范围内。
- 未修改 `kb_documents.content` 或 `outline`，未重建 outline，未执行全量 rechunk。

---

## 13. Leaf-only 清理与 Chunker 现状复核（2026-08-18）

### 13.1 本轮确定的设计口径

- 自动同步链路暂不作为当前重点，允许知识库暂时不更新；
- `kb_documents.content` 继续作为 Cleaner 处理后的 Markdown 正文源；
- Cleaner 暂时冻结，除非后续真实检索 Bad Case 能证明问题来自 Cleaner；
- 初始召回和向量索引采用 leaf-only；parent 不建向量、不参与初始召回，只作为 leaf 命中后的可选上下文扩展；
- 旧方案只保留实验记录和可恢复备份，历史 chunk 数据可以清理；
- 后续坚持单变量、分步骤调整，先验证内容和结构保真，再评价检索效果。

### 13.2 旧 chunk 清理结果

执行前服务器状态：

| 项目 | 数量 |
|------|-----:|
| `kb_chunks` 总数 | 48,137 |
| 有效 leaf | 35,076 |
| parent chunk | 10,398 |
| 空 `doc_id` 历史 chunk | 2,663 |
| `chunk_vectors` | 39,356 |
| 空 `doc_id` chunk 对应 vector | 980 |
| parent 对应 vector | 3,300 |
| leaf → parent 关联 | 12,294 |

本次完成：

- 删除 10,398 个 parent chunk；
- 删除 2,663 个空 `doc_id` 历史 chunk；
- 删除上述 chunk 对应的 4,280 条 vector；
- 清空 12,294 个 leaf 的 `parent_id`；
- 未修改 `kb_documents`、Cleaner 后的 Markdown、有效 leaf 正文或 outline。

最终只读验收：

| 检查项 | 结果 |
|--------|------|
| `kb_chunks` | 35,076，全部为有效 depth-1 leaf |
| `chunk_vectors` | 35,076 |
| parent chunk | 0 |
| 空 `doc_id` chunk | 0 |
| 非空 `parent_id` | 0 |
| vector 无对应 chunk | 0 |
| chunk 无对应 vector | 0 |
| 有正文但无 leaf 的文档 | 0 |

当前数据库已经满足 leaf-only 和 chunk/vector 一一对应。此处是清理完成时的阶段记录；随后已修复 parent 精确映射与写库契约，最终口径见 13.8。生产库仍未生成 parent。

### 13.3 删除前备份与临时文件清理

删除前备份保留在服务器：

`/home/jz/zhr/backups/rag-leaf-only-20260818-104834`

| 文件 | 行数 | SHA-256 |
|------|-----:|---------|
| `deleted_chunks.jsonl.gz` | 13,061 | `813b8db0f9bb9f3d5044f6ade6454969835e1332b1294e3d56d1a0423dc7f248` |
| `deleted_vectors.jsonl.gz` | 4,280 | `cd3e348bd716a41b0ac2fc726cb0b463ecfdf03b92294f65c063d09805c216ce` |
| `deleted_chunk_ids.txt` | - | `d72ea8eafa4d4c0bbc1a80477ff3eace22e23f256217ae5c9d00358d4d32cf4e` |
| `leaf_parent_links.jsonl` | 12,294 | `9e73468c1f12536ff48beb39d45a175efe6dd0db125e558e79ad5538d9553aa8` |

备份校验和已独立复核。该目录是本次删除操作的恢复依据，属于有意保留文件，不作为残留清理。

服务器临时文件已删除并确认不存在：

- `/tmp/rag_v2_candidate_chunker.py`
- `/tmp/rag_v2_repair_dryrun.json`
- `/tmp/test_chunker.py`

本地本轮生成的 `/tmp` 审计脚本也已清理。

### 13.4 Cleaner 结论

- 标准 Markdown pipe table 的表头、分隔行、列管道、行顺序和单元格内容能够保留；
- 整篇被转义的 Markdown 表格能够恢复；
- 原生 HTML `<table>` 仍保留为 HTML，不会被规范化成 Markdown pipe table；
- 既有 100 篇服务器审计为 100/100 幂等、100/100 表格行保留；
- 2026-08-18 本地复核：22 个 Cleaner 专项测试全部通过。

因此 Cleaner 当前不是主要矛盾，保持冻结。后续发现表格结构问题时，应先区分问题发生在 Cleaner 输出阶段还是 Chunker 跨 leaf 切分阶段。

### 13.5 Chunker 已确认问题

#### 1. Chunker 与 embedding tokenizer 不一致

当前 `chunker.py` 使用 `cl100k_base` 计数并以 512 为上限，实际 embedding 模型是 `BAAI/bge-small-zh-v1.5`。对当前 35,076 个 leaf 使用真实 BGE tokenizer 全量只读审计：

| 指标 | 结果 |
|------|-----:|
| BGE token 超过 512 的 leaf | 1,158（3.30%） |
| 受影响文档 | 481 |
| 最大 BGE token | 1,711 |
| 超限 leaf 中包含 pipe table | 469 |
| 表格内容占主导 | 398 |
| 包含 fenced code | 151 |
| 包含超过 1,000 字符的单行 | 92 |
| ASCII 内容占主导 | 1,071 |

数据库保存的正文没有因此删除，但 embedding 可能截断 leaf 尾部。数据库中 `token_count > 512` 为 0 只能证明 `cl100k_base` 计数未超限，不能证明 BGE 不截断。

#### 2. Parent 定位和写库契约不准确

`chunk_document()` 对超过 3,000 字符的文档生成 parent 是预期行为：leaf 用于初始召回和 embedding，parent 用于命中后的上下文扩展。问题不在“生成 parent”，而在原结果只提供 `section_path`，没有声明每个 parent 对应的具体 leaf；多个写库入口因此会错误关联或完全不设置 `parent_id`。该口径在 13.8 中修正并完成代码修复。

#### 3. 超长表格和代码块的结构可能被破坏

当前超长原子块最终仍会进入通用 `_fixed_window()`。2026-08-18 本地最小复现结果：

- 120 行长表格的表头、分隔行和 120 个数据行内容都还在，但表头只存在于第一个 leaf，后续 leaf 单独看不是完整 Markdown 表格；
- chunk 拼接结果与原始表格不是严格字符级一致；
- 长 fenced code 的可见正文仍在，但段落 `.strip()` 会破坏缩进，中间 leaf 也没有独立的围栏；
- 因此当前能证明“主要可见内容未静默丢失”，不能证明“Markdown/代码结构完全保真”。

该问题属于 Chunker，不推翻 Cleaner 对标准 Markdown 表格的保真结论。

#### 4. 当前测试覆盖不足

- Chunker 只有 4 个专项测试；2026-08-18 本地执行全部通过；
- 其 token 上限断言调用 Chunker 自己的 `count_tokens()`，无法发现 BGE tokenizer 超限；
- 现有表格测试只检查 marker 是否存在，没有检查跨 leaf 表头、行结构和字符级内容保真；
- 尚缺 leaf-only、不破坏代码缩进、真实 BGE token 上限和确定性切分测试。

#### 5. 小块合并可能模糊章节元数据

`_merge_tiny_leaves()` 可以跨相邻 section 合并内容，并以较长的 `section_path` 作为合并结果路径。正文仍在，但章节归属可能不准确。该项优先级低于 tokenizer、leaf-only 和表格/代码结构问题。

### 13.6 下一步执行顺序

为避免多变量同时变化，按以下顺序推进：

1. **修复 Parent 链路代码**：建立精确 child 映射、统一写库、leaf-only embedding 和初始召回；结果见 13.8，不重建数据库。
2. **真实 BGE 计数候选**：使用与 embedding 相同的 tokenizer，先以 480 BGE token 作为安全上限；只做 dry-run。
3. **结构感知切分**：表格按行分组并为后续 leaf 重复表头；代码按行分组并保持缩进、补齐围栏；超长单行使用明确兜底。
4. **定向验证 481 篇**：要求所有新 leaf 不超过安全上限、内容覆盖完整、表格行 100% 保留、首尾 marker 保留、输出确定且 leaf 数量无异常膨胀。
5. **人工确认后定向写库**：重建受影响 leaf、对应 parent 和 leaf vectors；parent 不建 vector。
6. **最后再评估检索效果**：建立当前版本评测集，对比 parent expansion 与 sibling expansion。

截至 13.6 只记录 2026-08-18 已完成事实和当前决策；除已授权的旧 chunk 清理外，没有执行新的 rechunk、embedding 或正文修改。

### 13.7 未启用的 v2 空表清理（2026-08-18）

多模态扩展设计曾预建 `kb_documents_v2`、`kb_blocks`、`kb_assets`、`kb_chunks_v2`。当前代码没有这些表的读写入口，四张表均为 0 行，且外键引用只存在于这四张表内部。

删除前已备份完整建表 DDL 和外键清单：

`/home/jz/zhr/backups/rag-v2-empty-schema-20260818-113452`

| 文件 | SHA-256 |
|------|---------|
| `schema.sql` | `d5c5ce6062894bb29527f52b5ee57dedcce3689d884cd0b945cf11eeb1eb37fe` |
| `manifest.json` | `586e2a845fc5a3f1480995af0854f16ebe490cb484a0dfc3f94a508e4f05f801` |

按外键依赖顺序删除：

1. `kb_assets`
2. `kb_chunks_v2`
3. `kb_blocks`
4. `kb_documents_v2`

独立复核结果：四张目标表均已不存在；核心 RAG 数据删除前后保持一致：

| 核心表 | 删除前 | 删除后 |
|--------|-------:|-------:|
| `kb_documents` | 6,817 | 6,817 |
| `kb_chunks` | 35,076 | 35,076 |
| `chunk_vectors` | 35,076 | 35,076 |

本次只删除未使用的空表，没有修改正文、leaf、vector、Cleaner、Chunker 代码或检索链路。需要恢复空表结构时可使用上述 `schema.sql`。

### 13.8 Parent 链路代码修复（2026-08-18）

本次修正“leaf-only”的准确含义：只允许 leaf 参与初始召回和 embedding；parent 可以生成并写入 `kb_chunks`，但只作为 leaf 命中后的支持上下文，不建立 vector。当前 Chunker 暂停继续调整，因此该能力保持代码就绪、生产未启用。

已完成四类修复：

1. `chunker.py` 为每个 parent 输出准确的 `child_chunk_indexes`，不再让写库层根据 `section_path` 猜测关系；
2. 新增 `chunk_storage.py` 作为共享持久化入口，`routes_v3.py`、`auto_sync.py` 和手动 rechunk 脚本统一按明确 child indexes 设置 leaf 的 `parent_id`；
3. `embedder.py` 默认只处理 `depth=1`，所有生产调用均显式传入 `depth=1`，手动 reembed 的孤儿清理也只把 leaf ID 视为有效 vector；
4. MySQL FULLTEXT、SQLite FTS 和向量结果回查均在初始召回阶段过滤 `depth=1`，避免 parent 挤占 leaf 候选。

同时修复手动 `rechunk_and_embed.py` 中使用不存在的 `KbDocument.doc_id/node_type` 字段，以及 rechunk 后未删除旧 vector 的问题。

新增回归覆盖：

- 同一章节产生多个 parent 时，每个 parent 声明准确且不重叠的 child leaf；
- parent 内容严格等于声明的 child leaf 组合；
- 共享写库后每个 leaf 只指向正确 parent；
- 一个 leaf 被多个 parent 声明时拒绝写入；
- embedding 默认深度为 1；
- MySQL/SQLite 关键词召回 SQL 包含 leaf 深度过滤；
- 向量候选回查 MySQL 元数据时再次过滤 leaf 深度。

验证结果：

- `python3 -m unittest discover -s tests -p 'test_*.py'`：51/51 通过；
- 相关 Python 文件 `py_compile` 通过；
- `git diff --check` 通过；
- 全部 `embed_chunks()` 生产调用已静态复核为 `depth=1`。

本次没有连接或修改生产数据库，没有 rechunk、没有生成 parent、没有重建 vector，也没有部署。当前数据库仍保持 35,076 个 leaf 和 35,076 个 leaf vector；待 BGE tokenizer 与结构感知切分稳定后，再按人工确认的范围重建 leaf、parent 和关联。
