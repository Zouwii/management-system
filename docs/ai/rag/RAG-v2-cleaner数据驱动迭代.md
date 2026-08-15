# RAG v2：Cleaner 数据驱动迭代

> 状态：100 篇审计完成，改造方案待实施
> 更新：2026-08-10
> 范围：服务器 Markdown 原文 → `clean_markdown()` → `kb_documents.content`
> 不包含：outline 提取、chunk 切分、embedding 和检索排序

## 1. 结论

Cleaner 已经具备可用的保守清洗基线，但还不能被视为完成。

100 篇去重文档审计表明：

- 100/100 从当前磁盘原文重新清洗后与数据库 `content` 完全一致；
- 100/100 满足幂等性；
- 100/100 保留原始 Markdown 表格行数量；
- 100/100 将每张 Markdown 图片转换为一个占位符；
- 99/100 fenced code block 文本完全一致，1 篇只发生 NBSP 到普通空格的变化；
- 词汇保留率中位数为 99.76%，最低为 79.19%。

当前主要风险不是大面积正文丢失，而是少量规则会改变技术词或丢失链接语义：

1. 相邻 `<span>` 无条件插入空格，会把 `protoc`、`instant`、`energyMode` 等词拆开；
2. `![有意义标题](钉钉文档链接)` 被统一当作图片，标题会被 node id 占位符替代；
3. 整篇被转义的 Markdown 未恢复，导致 `\#`、`\|` 无法成为标题和表格；
4. 代码块虽然被保护，但保护前的全局 NBSP 规范化仍会修改代码块内容。

因此下一步应先围绕已确认 Bad Case 做小步规则修复和回归验证，不应直接重写全部解析链路。

## 2. 原有设计与实现关系

### 2.1 已有设计

Cleaner 不是没有设计。已有资料包括：

- [Markdown 与图片多模态检索设计](./RAG-v2-markdown-multimodal-design.md)：定义原始层、AST block、HTML 白名单和图片资产；
- [研发项目与模块知识助手设计](./RAG-v2-研发项目知识助手设计.md)：规定保留标题、列表、表格、链接和人员上下文；
- [文档清洗与层级切分工作记录](./RAG-v2-文档清洗与层级切分工作记录.md)：记录 cleaner v1、样本验证和全量导入过程；
- [Markdown 清洗 v1 样本](./samples/markdown-cleaning-v1/README.md)：5 类原文、清洗稿和逐行 diff；
- `backend/tests/test_kb_markdown_cleaner.py`：现有 10 个规则级回归测试。

原设计的关键原则是：

```text
不可变原始 Markdown
    → Markdown AST / HTML 白名单规范化
    → source_markdown + text_normalized
    → outline / chunk / retrieval
```

其中明确要求：

- 原文和规范化文本分层保存；
- 标题、列表层级、表格边界、版本号和字段名不能误删；
- 解析采用 Markdown AST，不能只依赖字符串正则；
- 未知 HTML 保留可见文本并记录 warning；
- 图片保留来源关系，不能只留下无法回溯的文本。

### 2.2 当前实现的简化

当前 `cleaner.py` 是一个正则驱动的保守清洗器：

```text
normalize basic
    → protect fenced code
    → convert HTML lists
    → replace images with placeholders
    → remove/normalize inline HTML
    → compact blank lines
    → restore fenced code
```

它完成了 v1 所需的大部分格式清理，但与原设计存在四个差异：

| 原设计 | 当前实现 | 影响 |
|---|---|---|
| 原文不可变保存 | `kb_documents.content` 直接保存清洗稿，原文依赖服务器文件 | 数据库内无法独立审计和重放 |
| Markdown AST | 正则逐行处理 | 无法可靠区分链接、图片、代码、HTML 和普通文本边界 |
| `source_markdown` 与 `text_normalized` 分离 | 只有一个 content 字段 | 清洗错误会直接传递到 outline 和 chunk |
| parser version/checksum | 未随 content 持久化 | 规则升级后难以判断哪些文档需要重建 |

这说明当前实现是为了先跑通链路采用的 v1 简化方案，不是原设计的完整落地。

另外，v1 样本 README 中记录了 `build_samples.py` 的重建命令，但该脚本目前已不在样本目录中。现有 5 篇 diff 可以阅读，却不能按文档中的命令重复生成。这也是本轮需要补齐固定 canary、审计脚本和版本记录的原因。

## 3. 100 篇审计设计

### 3.1 抽样原则

本轮不是简单随机抽 100 篇，而是“代表性样本 + 风险定向样本 + 已知 Bad Case”。所有文档按清洗后正文 SHA-256 去重。

| 分层 | 数量 | 目的 |
|---|---:|---|
| 短文档，≤500 字符 | 15 | 检查空内容、短表格和导出噪声 |
| 中文档，501–3000 | 20 | 覆盖常规说明、排查文档和小型 PRD |
| 长文档，3001–10000 | 15 | 检查 HTML、图片和代码混排 |
| 超长文档，>10000 | 10 | 检查大文档稳定性 |
| 表格风险 | 8 | 至少 20 行表格 |
| 图片风险 | 7 | 至少 3 个图片占位符 |
| 代码风险 | 8 | 至少 1 个 fenced code block |
| 转义风险 | 8 | 存在 `\#` 或行首 `\|` |
| 超大文档风险 | 8 | 至少 30000 字符 |
| 已确认 Bad Case | 1 | 保留有意义链接标题丢失案例 |
| **合计** | **100** | 100 份不同正文 |

样本覆盖 8 个工作区。抽样使用固定随机种子 `20260810`，只接受能够在磁盘找到原文且重新清洗后与数据库 content 完全一致的文档。

风险定向样本用于发现问题，不能直接用其问题比例推断全库发生率。

### 3.2 指标

| 指标 | 用途 | 注意事项 |
|---|---|---|
| DB 重放一致性 | 验证原文、代码版本和数据库 content 对齐 | 不代表规则本身正确 |
| 幂等性 | 验证重复清洗不会继续改变文本 | 必须 100% |
| 词汇保留率 | 筛查潜在正文损失 | 图片 alt、HTML 属性和导出噪声会造成误报 |
| 标题数量 | 检查清洗是否删除 Markdown 标题 | 不评价 outline 是否正确 |
| 表格行数量 | 检查表格是否在 cleaner 阶段丢失 | 不评价 chunker 是否能切表格 |
| 图片→占位符数量 | 检查媒体引用是否成对保留 | 数量一致不代表语义一致 |
| fenced code 一致性 | 检查代码块是否被修改 | 空白规范化也应单独记录 |
| warning | 发现未知 HTML 或未闭合代码块 | 应持久化而非只在调用时返回 |

## 4. 审计结果

### 4.1 总体结果

| 指标 | 结果 |
|---|---:|
| 样本数 | 100 |
| 不同正文数 | 100 |
| 覆盖工作区 | 8 |
| 重新清洗与 DB 完全一致 | 100/100 |
| 幂等 | 100/100 |
| 表格行数量保持 | 100/100 |
| 图片与占位符数量一致 | 100/100 |
| fenced code 完全一致 | 99/100 |
| 字符保留比例中位数 | 81.13% |
| 词汇保留率中位数 | 99.76% |
| 最低词汇保留率 | 79.19% |

字符保留比例不能单独作为质量指标。图片 URL、HTML style 和导出容器会占用大量字符，删除它们会显著降低字符数，但不一定损失业务文本。

### 4.2 自动筛查结果

| 标记 | 文档数 | 复核结论 |
|---|---:|---|
| `LEXICAL_REVIEW` | 9 | 多数来自图片 alt 或导出噪声；至少 1 篇确认有语义丢失 |
| `ESCAPED_STRUCTURE` | 9 | 1 篇为整篇转义；其余多为局部转义，不能全局反转义 |
| `ASCII_SPAN_SPLIT_RISK` | 2 | 已确认存在技术词被插入空格 |
| `LINK_AS_IMAGE_ALT_LOSS` | 1 | 已确认有意义的钉钉文档标题丢失 |
| `CODE_CHANGED` | 1 | 仅 NBSP 变普通空格，语义未变但违反“代码块原样保护” |

这些标记可能重叠，不能相加后作为失败文档数。

## 5. Bad Case

### 5.1 相邻 span 拆坏技术词

当前规则会把所有相邻样式 span 之间插入一个空格，以避免两个文本片段粘连：

```html
<span>p</span><span>rotoc</span>
```

当前输出：

```text
p rotoc
```

原始语义应为：

```text
protoc
```

已观察到的同类内容包括：

- `protoc`；
- `instant`；
- `NodeInstant`；
- `factsheetRequest`；
- `energyMode`。

根因是规则无法判断 span 边界表示“样式切换”还是“词语边界”。这类问题必须结合左右字符判断，不能固定加空格。

### 5.2 有意义链接被当作图片

“交接清单”中存在：

```markdown
![tb迁移](https://alidocs.dingtalk.com/i/nodes/...)
![tb前后端部署](https://alidocs.dingtalk.com/i/nodes/...)
![scan-safer测试文档](https://alidocs.dingtalk.com/i/nodes/...)
```

这些 URL 指向钉钉文档节点，不是图片资源。当前 cleaner 只看 `![]()` 语法，把它们转换为图片占位符，并优先使用 URL 路径末尾的 node id，导致 `tb迁移`、`scan-safer测试文档` 等可检索语义丢失。

需要按照 URL 类型分类：

- 图片资源 URL → 图片占位符，同时保留 alt；
- 钉钉 node URL → 文档链接，保留标题和 URL；
- 无法判断 → 保留原始 Markdown 并记录 warning。

### 5.3 整篇转义 Markdown

“错误码示例接口”包含：

```text
\# JState 错误码 614002：地图异常
\## 1 错误结论
\| 字段 \| 内容 \|
```

Cleaner 当前原样保留这些转义字符，导致后续无法识别标题和表格。

不能对所有反斜杠做全局删除，因为其他文档中的 `\|`、`\#` 可能来自命令、正则或合法转义。建议只在文档满足“结构性转义占主导”时进入整篇反转义分支，例如：

- 没有正常 Markdown 标题，但存在多条行首 `\#`；
- 没有正常表格，但存在连续多行 `\|...\|`；
- 反转义后的结构可以通过 Markdown parser 验证；
- fenced code 内永不执行该规则。

### 5.4 代码块空白被修改

1 篇文档的 JSON code block 中 NBSP 被替换为普通空格。业务语义没有变化，但当前注释和测试口径声称 fenced code 不参与清洗。

需要明确选择一种契约：

- 严格保真：先保护代码块，再做包括 NBSP 在内的全部规范化；
- 检索规范化：允许统一代码空白，但在 `stats` 中记录变化。

对于作为知识库事实源的 content，推荐严格保真。

### 5.5 指标误报

部分词汇保留率低并不代表正文损坏。例如含 100 张图片的测试文档，主要减少的是重复 `image.png` 和长 URL。

因此词汇保留率只能作为人工复核触发器，不能单独作为失败判定。至少需要同时查看：

- 图片数量是否一致；
- 丢失词是否只是通用图片 alt；
- 表格和标题数量是否变化；
- 是否出现有意义的链接标题丢失；
- 是否存在技术标识符拆分。

## 6. 数据驱动迭代流程

Cleaner 后续按固定闭环演进：

```text
生产文档/检索 Bad Case
    → 归因到 cleaner、outline、chunker 或 retrieval
    → Bad Case 加入固定 canary
    → 写最小回归测试
    → 修改一条规则
    → 跑单测 + 100 篇审计
    → 比较 candidate 与 baseline
    → 通过后记录 parser_version 并重建受影响文档
```

每个规则变更必须记录：

| 字段 | 说明 |
|---|---|
| Case ID | 稳定编号 |
| node_id / content hash | 可重复定位样本 |
| 原始片段 | 修改前证据 |
| baseline 输出 | 当前行为 |
| candidate 输出 | 候选行为 |
| 预期不变量 | 不应变化的表格、图片、代码或正文 |
| 影响范围 | 全库命中数量和文档类型 |
| 下游结果 | outline/chunk/retrieval 是否改善 |
| parser_version | 上线规则版本 |

## 7. 迭代优先级

### P0：已确认语义错误

1. span 边界改为按字符语义决定连接或空格；
2. 区分图片 URL 与钉钉文档 node URL，保留有意义 alt；
3. 增加结构性整篇转义检测，只在高置信度条件下反转义；
4. 明确并实现 fenced code 的严格保护顺序。

### P1：可审计与可重建

1. 保存 `raw_content` 或稳定的原文 URI + checksum；
2. 保存 `cleaner_version`、`cleaned_hash`、warnings 和 stats；
3. 不再让 `kb_documents.content` 同时承担原始事实和规范化正文两个角色；
4. 建立单文档重放和按 cleaner version 重建能力。

### P2：AST 迁移评估

原设计要求 Markdown AST，方向仍然正确，但不建议在没有对照数据时直接全量替换现有 cleaner。

先选 20 篇高风险 canary，对比：

- 当前正则 cleaner；
- Markdown AST + HTML 白名单 candidate；
- 标题、表格、列表、链接、代码、图片和词汇保留；
- 下游 outline 和 chunk 覆盖率。

只有 AST candidate 在这些指标上稳定优于 baseline，才进入全量迁移。

## 8. 验收标准

每次 cleaner 规则升级至少满足：

1. 现有单元测试全部通过；
2. 100 篇固定 canary 全部可重放；
3. 幂等率 100%；
4. 表格行丢失 0；
5. 图片/链接类型误判 0；
6. fenced code 非预期变化 0；
7. 已确认 span 拆词 Bad Case 归零；
8. 整篇转义文档恢复结构，同时局部合法转义不受影响；
9. 所有新增 warning 可统计、可定位；
10. 至少抽查 10 篇 candidate diff 后再批量重建。

Cleaner 验收后再重新生成 outline 和 chunk。否则 documents 层的格式错误会继续被误判为 chunker 问题。
