# RAG v2：Markdown 与图片多模态检索设计

> 状态：设计稿
> 日期：2026-07-30
> 适用范围：`/home/jz/zhr/markdown/` 导出的钉钉 Markdown 文档，以及后续同类 Markdown 知识库

> **范围调整（2026-07-31）**：本文保留为多模态扩展方案，不作为当前 V1 实施范围。当前 V1 聚焦研发人员、任务、方案、项目节点、验收表和代码仓库文档，图片只保留回链。现行设计见：[RAG v2：研发项目与模块知识助手设计](./RAG-v2-研发项目知识助手设计.md)。

## 1. 结论先行

新的 RAG 不应直接对原始 `raw_json` 或整篇 Markdown 做固定长度切片。推荐采用下面的链路：

```text
原始 Markdown
    -> Markdown AST + HTML 清洗
    -> 规范化 blocks（标题、段落、列表、表格、链接、图片）
    -> 文本 chunk + 图片 asset + OCR/视觉 artifact
    -> 关键词召回 + 向量召回 + RRF
    -> Cross-Encoder 重排
    -> 父块/相邻块扩展
    -> LLM 回答与原图引用
```

核心决策：

| 决策 | 方案 |
|---|---|
| 原始事实来源 | 原始 Markdown；`raw_json` 只作为审计副本 |
| 解析方式 | Markdown AST，兼容 HTML，不使用正则直接切字符串 |
| 检索粒度 | 220-420 token 的叶子 chunk；保留 600-1200 token 的父级上下文 |
| 表格处理 | 表头注入每个行组，禁止按字符截断表格行 |
| 图片处理 | 解析 URL、缓存原图、按类型执行 OCR 或视觉摘要 |
| 图片检索 | OCR 文本和视觉摘要独立建索引，并关联到原文 block |
| 向量模型 | 先稳定中文 embedding + reranker，再评估多模态向量模型 |
| 更新方式 | 文档 checksum 驱动的幂等增量重建，支持单文档全量重建 |

## 2. 实际 Markdown 数据特征

对服务器 `/home/jz/zhr/markdown/` 中的文档抽样后，输入不是单一的纯 Markdown，而是 Markdown、HTML 和外部资源的混合格式。

### 2.1 有效语义

- `#`、`##`、`###` 标题构成文档的主要层级和语义路径。
- 普通段落包含定义、规则、例外条件和计算公式。
- 无序/有序列表经常表达流程、约束和多个并列条件。
- Markdown 表格包含岗位、状态、参数、版本等结构化知识。
- `[标题](url)` 是文档导航或关联文档关系。
- `![image.png](https://... "")` 是图片资源关系；图片本身可能承载界面、流程或表格信息。

### 2.2 需要清洗的格式

常见的 `<ul><li>...</li></ul>`、`<br>`、`<span style="...">` 是导出格式，不应原样进入 embedding。处理时需要保留列表层级和换行，但删除颜色、字体、边距等视觉样式。

标题中的 `**`、图片的无意义 alt（例如 `image.png`）、空的图片 title 也不应作为检索关键词。

### 2.3 不能误删的内容

以下内容虽然看起来像格式，也有检索价值：

- 表头与表格行之间的对应关系；
- 列表的编号和嵌套层级；
- 标题路径；
- 版本号、日期、状态名、字段名、公式中的数字；
- 图片所在的段落和标题；
- 文档之间的链接关系。

版本修订表可以保留，但标记为 `revision_history`，默认检索权重低于当前正文；用户明确查询版本变更时再提高权重。

## 3. 规范化层

### 3.1 不可变原始层

原始 Markdown 每次同步都保存以下信息：

```text
document_id
source_path
source_url（如果有）
content
content_hash
source_modified_at
ingested_at
parser_version
```

`raw_json` 不参与正文解析和检索。它可以作为 `source_payload` 保留，用于问题追踪，但不应成为线上 RAG 的事实来源。

### 3.2 AST block 类型

解析器将每个文档转换为有序 block：

```text
document
  heading(level, text)
  paragraph(text)
  list(ordered, items[])
  table(headers[], rows[])
  code(language, text)
  quote(text)
  link(text, url)
  image(alt, url, title)
```

每个 block 至少保存：

```text
block_id, document_id, ordinal
block_type, heading_path, parent_block_id
text_normalized, source_markdown
asset_ids, parser_version
```

`source_markdown` 用于回溯，`text_normalized` 用于切块和检索。二者不能混为一个字段。

### 3.3 HTML 清洗规则

使用 Markdown 解析器先得到 AST，再对 HTML 节点做白名单转换：

| 输入 | 规范化结果 |
|---|---|
| `<br>` | 一个换行 |
| `<li>` | 一个带层级的列表项 |
| `<ul>/<ol>` | 列表容器 |
| `<span style=...>` | 仅保留文本 |
| `<strong>/<b>` | 普通文本，必要时保留强调标记 |
| 未知 HTML | 保留可见文本，记录 warning |
| 脚本、样式、空节点 | 丢弃 |

不要用简单的 HTML 标签删除替代解析，否则相邻列表项会粘连，表格和公式会损失边界。

## 4. Chunk 设计

### 4.1 父块和叶子块

采用“小块召回，大块生成”的父子结构：

- 叶子 chunk：用于关键词和向量检索，目标 220-420 token，硬上限 512 token。
- 父块：同一章节下的完整语义单元，目标 600-1200 token，用于补充 LLM 上下文。
- 相邻块：同一 `heading_path` 下，允许向前/向后扩展一个叶子块。

当前 embedding 模型的最大输入长度有限，不能再使用 800-1200 token 的块直接做向量。超过 512 token 的文本即使入库，也可能在 embedding 时被截断。

### 4.2 通用正文

按标题边界和段落边界切分，禁止从句子中间切断。建议规则：

1. 先按标题生成章节。
2. 章节内按段落、列表项、引用块累加。
3. 达到 220-420 token 后结束一个 chunk。
4. 只有超长单段才使用句子级滑窗，重叠 40-80 token。
5. 每个 chunk 注入短元数据，不把长路径重复多次：

```text
文档：本体开发部制度规范
章节：任务布置 > 有效工时评估
内容：...
```

### 4.3 标题和小节

标题本身不能单独成为一个普通 chunk。应将标题作为 `heading_path` 注入到其下所有叶子 chunk。

短小章节可以与下一个同级章节合并，但不能跨越高价值边界，例如“定义”不能和“例外规则”无标识地拼接。

### 4.4 列表

列表项是最小语义单元。一个列表项超过上限时按句子切分，否则按多个列表项聚合。

每个列表 chunk 要保留列表上下文，例如：

```text
章节：任务单编辑说明
主题：状态
- 1. 创建任务后状态为“创建中”
- 2. 确认工时后状态为“未完成”
```

不要把 `<li>` 标签本身放入向量文本。

### 4.5 表格

表格是当前 Markdown 中最容易被错误切分的类型。每个行组必须重复表头，并转为可读的键值形式：

```text
表格：有效工时类型
有效工时类型=方案设计；适用范围=技术方案、算法方案；典型产出=方案文档、架构图
有效工时类型=开发实现；适用范围=功能开发、算法实现；典型产出=代码、测试结果
```

规则：

- 一行不能跨 chunk。
- 行组目标 200-420 token，按行边界结束。
- 宽表只保留非空单元格，但保留列名。
- 表格前的标题、说明段和表格后的约束分别保留 `table_context`。
- 表格有合并单元格时，将最近的非空父级单元格向下填充。

### 4.6 代码、公式和版本历史

- 代码块按函数、配置段或自然空行分割，不按普通段落处理。
- 公式保留原始文本，同时生成一份纯文本解释字段；不要仅依赖公式符号召回。
- 版本历史单独标记 `revision_history`，在检索时默认乘以 0.5 的权重。
- 目录索引主要用于导航图，不作为普通正文大量注入上下文。

## 5. 图片处理

### 5.1 图片不是一个问题，而是三个问题

图片需要同时解决：

1. 找到图片：解析 Markdown image block，获得 URL、alt、所在章节和顺序。
2. 理解图片：根据图片类型做 OCR、表格识别或视觉摘要。
3. 展示图片：回答时返回稳定的原图或缓存 URL，而不是只返回 OCR 文本。

### 5.2 图片资产表

建议建立独立的 `kb_assets`：

```text
asset_id
document_id
block_id
heading_path
ordinal
source_url
stored_uri
checksum
mime_type
width, height
alt_text
asset_type
ocr_text
ocr_json
vision_caption
processing_status
parser_version
```

`source_url` 是来源证据，`stored_uri` 是系统自己的缓存地址。不能长期依赖第三方临时 URL；下载失败时保留失败状态和重试次数。

图片 URL 下载必须有域名白名单、超时、大小限制和 MIME 校验，避免把 Markdown 中的任意 URL 当作内部资源下载。

### 5.3 图片分类与处理策略

| 类型 | 处理 | 是否建立检索文本 |
|---|---|---|
| UI 截图、扫描件 | 中文 OCR，保留文字框和置信度 | 是，独立 OCR chunk |
| 流程图、架构图 | OCR + 视觉模型描述节点和关系 | 是，OCR 和 caption 分开 |
| 表格截图 | OCR 表格结构化识别 | 是，生成行列文本 |
| 普通照片、装饰图 | 简短视觉 caption 或跳过 | 低优先级 |
| 无法下载/损坏图片 | 记录状态和原始链接 | 否，不能伪造内容 |

因此答案是：要做 OCR，但不能只做 OCR。OCR 负责“图中写了什么”，视觉摘要负责“图表达了什么关系”。

推荐先使用本地中文 OCR（例如 PaddleOCR 同类方案），只对流程图和复杂截图调用视觉模型，控制成本和延迟。

### 5.4 图片如何与文本 chunk 关联

图片所在正文 chunk 增加短引用，不把完整 OCR 内容硬塞进去：

```text
[关联图片 asset_id=asset-123]
图片说明：任务有效工时填写界面
```

另外为 OCR 和视觉摘要创建独立 artifact chunk：

```text
asset_id=asset-123
文档=本体开发部制度规范
章节=有效工时记录
类型=image_ocr
内容=有效工时、任务状态、父任务、子任务……
```

这样做有三个好处：文本问题可以命中图片中的字段；图片问题可以命中图片 artifact；回答时仍能反向找到原图。

`alt_text=image.png` 这类文件名没有语义价值，应从默认 embedding 文本中剔除。

## 6. 检索链路

### 6.1 查询预处理

先做轻量分析，不要一开始就让 LLM 改写所有查询：

- 提取版本号、字段名、错误码、人员名、产品名等精确词。
- 判断是否有“图片、截图、图中、界面、流程图”等图片意图。
- 识别时间、文档类型、知识库和权限过滤条件。
- 仅在首轮召回为空或置信度低时，启用查询扩展/分解。

### 6.2 多路召回

第一版建议三路：

| 通道 | 召回内容 | top-k |
|---|---|---:|
| BM25/全文 | 正文、字段名、版本号、OCR 文本 | 30 |
| Dense embedding | 正文、表格行组、OCR、视觉摘要 | 30 |
| 标题/路径 | 文档标题、章节路径、链接标题 | 10 |

三路使用带权 RRF 融合：正文关键词和 dense 为主，标题/路径作为补充。所有结果先做 ACL、知识库、文档状态过滤。

### 6.3 重排和上下文组装

1. RRF 后保留 30 个候选。
2. 使用 Cross-Encoder 重排到 8-12 个。
3. 对命中的叶子 chunk 扩展其父块或同章节相邻块。
4. 同一文档最多保留 3 个证据块，避免一个长文档挤占全部上下文。
5. 对重复内容做去重，对相似但不同章节使用 MMR 保证覆盖面。
6. 总上下文控制在 6000-8000 token，并在每块前保留文档名和章节路径。

图片意图查询命中 `image_ocr` 或 `image_caption` 时，返回对应原图引用。只有用户明确要求看图，或视觉摘要置信度足够高时，才把图片本体发送给多模态模型。

### 6.4 结果与引用

每个答案证据必须包含：

```text
document_id, title, source_path, heading_path
chunk_id, asset_ids, source_url/stored_uri
score, retrieval_channel
```

LLM 只使用召回的证据，不自行拼接未检索的图片 URL。图片引用和文本引用分别展示，避免用户只能看到一段 OCR 而无法打开原图。

## 7. 推荐数据表

### 7.1 文档和 block

```sql
kb_documents_v2(
  id, source_path, title, content, content_hash,
  source_modified_at, parser_version, acl_json, status
)

kb_blocks(
  id, document_id, ordinal, block_type, heading_path,
  parent_block_id, normalized_text, source_markdown,
  metadata_json
)
```

### 7.2 图片和 artifact

```sql
kb_assets(
  id, document_id, block_id, source_url, stored_uri,
  checksum, mime_type, width, height, alt_text,
  asset_type, processing_status, metadata_json
)

kb_asset_artifacts(
  id, asset_id, artifact_type, content, confidence,
  engine, engine_version, metadata_json
)
```

`artifact_type` 至少包含 `ocr`、`caption`、`table`。

### 7.3 Chunk 和向量

```sql
kb_chunks_v2(
  id, document_id, parent_block_id, chunk_index,
  chunk_type, heading_path, content, token_count,
  asset_ids_json, metadata_json, content_hash
)

kb_embeddings_v2(
  chunk_id, model_name, model_version, dimension, embedding
)
```

向量表必须记录模型版本；换 embedding 模型时建立新版本，不要覆盖旧向量后失去可比性。

## 8. 增量更新和重建

每个文档以 `content_hash + parser_version + chunker_version` 作为处理版本。

```text
扫描文件
  -> checksum 未变化：跳过
  -> checksum 变化：删除该文档 v2 block/chunk/asset 结果
  -> 重新解析 Markdown
  -> 重新下载或复用图片（按 URL/checksum）
  -> OCR/视觉处理
  -> 重建 chunks
  -> 批量生成 embedding
```

不要只对“本次同步返回 changed_ids 的文档”切片。首次迁移必须支持 `rebuild_all`，因为历史文档可能已经入库但从未产生 chunk。

旧表不直接删除，先建立 v2 表并做双写或离线重建；通过 canary 查询确认召回质量后再切换线上读取。

## 9. 参数基线

| 参数 | 初始值 | 说明 |
|---|---:|---|
| leaf target | 220-420 token | 向量检索粒度 |
| leaf hard max | 512 token | 防止 embedding 截断 |
| sentence overlap | 40-80 token | 只在超长段落使用 |
| parent target | 600-1200 token | LLM 上下文扩展 |
| lexical top-k | 30 | BM25/全文 |
| dense top-k | 30 | 向量和 asset artifact |
| rerank candidates | 30 | Cross-Encoder 输入 |
| final evidence | 8-12 | 组装前去重 |
| same-document max | 3 | 防止单文档垄断 |
| context budget | 6000-8000 token | 视模型上下文调整 |

这些值必须通过测试集调参，不将实验报告中的单次 NDCG 数字当作生产保证。

## 10. 评测集和验收

测试集至少覆盖：

- 普通定义和规则问题；
- 表格中的字段、行和数值问题；
- 版本/日期/状态等精确匹配问题；
- 跨标题的流程问题；
- 图片 OCR 问题；
- 流程图和截图含义问题；
- 只给别名或口语描述的问题。

指标分为四类：

1. Recall@5、Recall@10、MRR、nDCG@5。
2. 证据块是否支持答案，不能只评估答案是否流畅。
3. 图片问题的 OCR 字段准确率、图片关联准确率。
4. 延迟、OCR 成本、缓存命中率和失败重试率。

上线前必须证明：

- 表格行不会被截断或与表头脱离；
- 命中图片 OCR 时能返回正确原图；
- 图片下载失败不会生成伪造 OCR；
- 旧文档和新文档使用同一套 checksum 规则可重复重建；
- 文档权限过滤在所有召回通道一致生效。

## 11. 从当前实现迁移

1. 保留现有同步接口，但把 Markdown 正文作为 v2 的输入；`raw_json` 降级为审计字段。
2. 实现 AST 解析、HTML 清洗、表格行组和图片 block 抽取。
3. 建立 `kb_documents_v2 / kb_blocks / kb_assets / kb_asset_artifacts / kb_chunks_v2`。
4. 对已有文档执行一次全量 `rebuild_all`，不要依赖增量 changed list。
5. 先启用正文 + OCR artifact，视觉摘要作为第二阶段能力。
6. 建立包含图片问题的检索测试集，与旧链路做离线对照。
7. 以 5%-10% 查询流量灰度 v2，比较召回、引用正确率和延迟。
8. v2 稳定后再清理旧向量表和旧 chunk 表。

## 12. 不在第一阶段做的事情

- 不直接把整张图片转成向量作为唯一检索方式。
- 不对所有图片无条件调用大模型 OCR/视觉分析。
- 不使用 HyDE、复杂 query decomposition 作为基础链路依赖。
- 不把整段 `raw_json`、HTML 样式或完整 base64 图片放进 embedding 文本。
- 不用固定字符数替代标题、列表和表格边界。

第一阶段的目标是建立可解释、可重建、能正确关联图片的文本+资产检索；多模态向量和复杂查询改写应在有评测数据后再加入。
