# RAG v2：文档清洗与层级切分工作记录

> 状态：v3 链路可用，已知问题待修 | 更新：2026-08-07
> 样本目录：服务器 `/home/jz/zhr/markdown/`  
> 关联设计：[RAG v2：Markdown 与图片多模态检索设计](./RAG-v2-markdown-multimodal-design.md)

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
