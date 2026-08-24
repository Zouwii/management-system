# RAG v3 切块策略调研

> 状态：阶段性调研结论，尚未进入生产改造
> 日期：2026-08-24
> 范围：Management-System 知识库清洗、结构提取、切块与向量检索

## 1. 结论摘要

当前 v2 的主要问题不是“块一定太小”，而是同一份 leaf 同时承担了结构保存、向量召回和回答上下文三个职责：

- 文件夹层级没有进入 embedding 文本；
- 本文目录多数只保存在 metadata，不能稳定影响向量召回；
- Markdown 正则提取目录会把代码、普通段落等误判成标题；
- 表格和代码可能被跨结构切断；
- 当前 `BAAI/bge-small-zh-v1.5` 的有效窗口是 512 token，部分 v2 leaf 已超过窗口并在编码时被截断；
- 生产库中混有历史切块结果，不能假定当前线上数据都由现版本 Chunker 生成。

因此，不建议继续把 v2 优化为“统一的约 1200 token 大叶子”，也不建议直接用当前 BGE-small 对 1200 token 内容做 embedding。

v3 推荐采用“结构块、检索投影、回答上下文”分层方案：

```mermaid
flowchart LR
    A[钉钉原生 Markdown / JSONML / Blocks] --> B[原生标题和 Block 结构]
    B --> C[上下文块<br/>目标约 900，最大 1200 BGE token]
    C --> D[检索投影<br/>最大 480 BGE token]
    D --> E[向量召回]
    E --> F[按 context_id 展开完整上下文]
    F --> G[重排、引用与回答]
```

每个检索投影和上下文块都应显式包含：

```text
知识库路径：研发专项知识库 / 进行中项目 / ...
文档：仿真平台http接口文档
本文目录：用户接口 > 新增用户
```

这是一套“钉钉式结构保留方案”，不是已经获取到的钉钉内部 AI 切块算法。钉钉开放接口能够确认原生 JSONML、outline、blocks 和节点层级，但没有暴露其内部向量切块结果。

## 2. 调研目标

本轮调研验证以下问题：

1. v2 Cleaner、目录提取和 leaf 切块在真实文档上的实际表现；
2. 钉钉是否提供比 Markdown 正则更可靠的结构数据；
3. “动态切块、约 1200 token、携带知识库路径和本文目录”的方案是否可复现；
4. 1200 token 与当前 embedding 模型窗口如何兼容；
5. v3 应继续优化 leaf，还是拆分检索单元和上下文单元。

## 3. 调研边界与证据等级

### 3.1 已确认事实

- 钉钉 MCP 可获取文档 Markdown、JSONML、outline 和一级 document blocks；
- JSONML 支持 `outline`、`range`、`section`、`tags` 等范围；
- 可通过节点接口获得文档所在知识库及文件夹层级；
- 六篇服务器真实文档已经下载到本地，并完成 v2 重放和 v3 候选切块；
- BGE-small tokenizer 下，v2 存在超过 512 token 的 leaf；
- v3 候选的上下文块均不超过 1200 token，检索投影均不超过 480 token。

### 3.2 尚不能直接确认

- 钉钉内部 AI 是否固定使用 1200 token 上限；
- 钉钉内部是否将文件夹路径、本文目录直接拼入 embedding 文本；
- 钉钉内部是否同时维护“小检索块 + 大上下文块”；
- 钉钉内部 embedding、重排及邻块扩展算法。

“约 1200 token 动态切块”目前来自产品侧观察。本调研验证的是该思路在现有系统中的可行实现，而非逆向得到钉钉内部算法。

## 4. 数据范围

### 4.1 服务器数据概况

- `kb_documents`：6,817 条，其中 4,749 条有正文；
- `kb_chunks`：35,076 个 depth=1 leaf；
- 现存 leaf 平均约 262.1 token，最大 512 token；
- `kb_nodes`：18,732 个节点，其中 6,218 个文件夹。

上述库存 token 统计使用当前数据库口径，并不等同于 BGE tokenizer 的实际输入长度。

### 4.2 六篇代表性样本

| 文档 | 类型 | 选择原因 |
|---|---|---|
| 速度仲裁 | 短篇技术文档 | 健康对照，包含正文、表格和代码 |
| 故障诊断三期需求分解方案 | 长需求文档 | HTML 和超长行较多 |
| 低代码算子字典 | 超长混合文档 | 标题、表格、列表、代码和图片混合 |
| 驱动相关ROS接口 | 表格型接口文档 | 生产库约 8.3 万字符但只有一个 leaf |
| AGV硬件维护指导书V1.7 | 图片密集文档 | 没有原生标题，用于检查假目录问题 |
| 仿真平台http接口文档 | API 文档 | 标题、表格、代码块密集 |

每篇样本均保留：服务器 Markdown 原文、钉钉原生 Markdown、JSONML、outline、一级 blocks 和文件夹路径。

## 5. 当前 v2 重放结果

本地使用当前 Cleaner、`_extract_outline_v2` 和 Chunker 对六篇原文重新执行，token 长度使用 BGE-small tokenizer 复核。

| 样本 | v2 leaf | BGE 最大 token | 超过512 | 原生标题 | v2目录 | 主要问题 |
|---|---:|---:|---:|---:|---:|---|
| 速度仲裁 | 5 | 336 | 0 | 0 | 1 | 短文被拆成多个较小 leaf |
| 故障诊断 | 52 | 516 | 1 | 9 | 9 | 存在超长行和截断风险 |
| 低代码字典 | 183 | 670 | 5 | 95 | 107 | 假目录、代码围栏和表格完整性问题 |
| ROS接口 | 128 | 1071 | 8 | 109 | 103 | 表格表头丢失，存在严重模型截断 |
| AGV维护 | 113 | 334 | 0 | 0 | 339 | 无原生标题却生成大量假目录 |
| 仿真HTTP | 35 | 442 | 0 | 60 | 119 | 代码中的 `#` 等内容被误判成目录 |

补充结构检查发现：

- 六篇样本中，文件夹路径进入 leaf 正文的数量为 0；
- `section_path` 多数仅作为 metadata 存储，没有进入 embedding 内容；
- 低代码字典有 52 个 leaf 的 Markdown 代码围栏不平衡；
- 仿真 HTTP 文档有 20 个 leaf 的代码围栏不平衡；
- ROS 接口有 15 个表格 leaf 缺少完整表头或分隔行；
- 六篇样本合计 14 个 leaf 超过 BGE-small 的 512 token 窗口。

### 5.1 三个典型 Bad Case

**AGV 维护指导书**

钉钉原生 outline 中没有 heading，说明它本质上是一篇图片和普通 block 组成的文档。v2 从清洗后的 Markdown 推导出 339 个目录，目录结构主要是启发式误判，不适合作为检索结构。

**仿真 HTTP 接口文档**

原生 heading 为 60 个，v2 识别为 119 个。部分 fenced code 内以 `#` 开头的内容被当成标题，同时代码在 leaf 边界处被切开。

**驱动相关 ROS 接口**

生产库中该文档约 8.3 万字符却只有一个 leaf；使用当前本地代码重新处理得到 128 个 leaf。这说明生产数据包含旧版或异常切块结果，v3 迁移不能只更新代码，必须重建索引并校验版本。

## 6. 钉钉原生结构调研

### 6.1 可利用的数据

钉钉开放能力可以提供：

- 文档节点及其父级文件夹，用于生成知识库路径；
- 原生 JSONML heading，用于生成本文目录路径；
- 原生 table、code、paragraph 等 block，用于结构感知切分；
- block ID，用于定位、扩展上下文和后续引用；
- Markdown，用于原文归档、展示和兼容回退。

### 6.2 JSONML 与 blocks 的使用顺序

推荐优先级：

1. 完整 JSONML；
2. 分 section/range 获取 JSONML；
3. 一级 document blocks；
4. 原生 Markdown；
5. Markdown 正则目录，仅作为最后兜底且标记低置信度。

AGV 样本的完整 JSONML 超过网关约 2 MB 响应限制，候选实现已自动回退到 1,450 个一级 blocks，并成功完成处理。这说明生产方案必须支持分页或 block fallback，不能只依赖一次性完整 JSONML。

## 7. v3 候选方案

### 7.1 数据模型

建议至少保留三类对象：

| 对象 | 作用 | 建议长度 |
|---|---|---:|
| Native block | 不可变的原生结构和引用锚点 | 按钉钉原生结构 |
| Context chunk | 提供完整语义、表格/代码结构和回答上下文 | 目标约900，最大1200 BGE token |
| Retrieval projection | embedding、向量召回和细粒度命中 | 最大480 BGE token |

核心关联字段建议包括：

- `document_id`；
- `context_id`；
- `projection_id`；
- `block_ids`；
- `folder_path`；
- `section_path`；
- `source_version`；
- `chunker_version`；
- `content_hash`。

### 7.2 动态切块规则

1. 先根据原生 heading 建立 section path；
2. 在同一 section 内按 block 顺序动态聚合；
3. 上下文块目标约 900 token，硬上限 1200 token；
4. section 变化时优先结束当前上下文块；
5. 单个超长 block 再按其类型拆分；
6. 表格按行拆分，每片重复表头；
7. 代码按行拆分，每片重新闭合 fenced code；
8. 普通文本依次按段落、换行、句子和 token 边界降级切分；
9. 上下文块进一步生成不超过 480 token 的检索投影；
10. 检索命中 projection 后，通过 `context_id` 返回完整上下文块。

### 7.3 为什么不是直接 embedding 1200 token

当前 BGE-small 的输入窗口约为 512 token。直接编码 1200 token 会发生截断：

- 块尾信息不参与向量；
- 标题、表头和关键参数可能被截掉；
- 代码和长表格的实际向量表示不完整；
- 看似减少了 chunk 数，实际召回可见内容反而变少。

1200 token 更适合作为“回答上下文”的上限，而不是当前模型下的“embedding 单元”上限。若未来替换成长上下文 embedding 模型，也应重新通过检索 A/B 决定是否合并两层，而不是仅按窗口长度调整。

## 8. 候选方案离线结果

| 样本 | 原生来源 | 上下文块 | 上下文最大 token | 检索投影 | 投影最大 token |
|---|---|---:|---:|---:|---:|
| 速度仲裁 | JSONML | 1 | 642 | 3 | 426 |
| 故障诊断 | JSONML | 19 | 1191 | 51 | 478 |
| 低代码字典 | JSONML | 81 | 1184 | 156 | 478 |
| ROS接口 | JSONML | 104 | 1192 | 162 | 478 |
| AGV维护 | Blocks fallback | 28 | 900 | 71 | 478 |
| 仿真HTTP | JSONML | 59 | 566 | 61 | 478 |

六篇样本均满足：

- 上下文块不超过 1200 BGE token；
- 检索投影不超过 480 BGE token；
- 所有上下文块包含知识库文件夹路径；
- 所有上下文块包含文档名和本文目录；
- 使用原生 heading，不为 AGV 样本生成 339 个启发式假标题；
- 超长表格按行拆分并重复表头；
- 超长代码块切分后保持围栏完整。

短文《速度仲裁》从 v2 的 5 个 leaf 变为 1 个 642-token 上下文块，并生成 3 个检索投影。这说明“回答上下文”和“检索粒度”拆开后，不需要在短叶子与完整语境之间二选一。

## 9. 当前效果评估

### 9.1 已经可以判断的部分

| 维度 | v2 | v3候选 | 阶段性判断 |
|---|---|---|---|
| 文件夹层级 | 不进入正文 | 每块显式携带 | v3 更适合层级型查询 |
| 本文目录 | metadata 为主 | 每块显式携带原生路径 | v3 结构信号更稳定 |
| 目录来源 | Markdown 启发式 | 原生 heading 优先 | v3 显著减少假目录 |
| 表格 | 可能丢表头 | 拆分时重复表头 | v3 结构完整性更好 |
| 代码 | 可能切断围栏 | 每片闭合围栏 | v3 结构完整性更好 |
| 模型窗口 | 部分 leaf 超限 | projection ≤480 | v3 与当前模型匹配 |
| 回答语境 | 受 leaf 大小限制 | 命中后展开 context | v3 上下文更完整 |

### 9.2 尚未完成的部分

目前尚未完成基于真实 query 的向量检索 A/B，因此不能将“结构更完整”直接表述为“召回率已经提升”。下一步应在相同 BGE-small 模型下比较：

1. v2 leaf 正文；
2. v2 leaf + 文件夹路径 + 文档名 + `section_path`；
3. v3 原生结构 retrieval projection。

首轮已准备 12 条查询，覆盖六篇样本的内容型和层级型问题。评估指标建议使用：

- 文档级 Hit@1、Hit@3、Hit@5；
- MRR；
- chunk/context 命中准确率；
- 表格、代码、层级查询分组结果；
- Top-K 上下文冗余率；
- 最终回答的引用正确率和信息完整率。

六篇、12 条查询只适合验证实现方向，不能作为生产收益结论。上线前应扩大到至少数十篇 canary 文档和现有真实问题集。

## 10. 生产建议

### 10.1 建议采用

- 保留钉钉原生 Markdown、JSONML/block ID 和节点路径，不只保存清洗后的纯文本；
- 原生 heading 是目录主来源，正则目录降级为低置信度兜底；
- context chunk 与 retrieval projection 分开存储；
- 当前 BGE-small 下将 projection 控制在约 480 token；
- 每个投影显式加入文件夹路径、文档名和本文目录；
- 表格、代码使用类型专属切分器；
- 命中 projection 后展开 context，必要时再扩展相邻 block；
- 给索引写入 `source_version`、`chunker_version` 和 hash，支持增量重建与问题追踪；
- v3 上线时重建 canary 文档索引，不复用无法确认版本的旧 leaf。

### 10.2 暂不建议

- 直接把所有 leaf 调成统一 1200 token；
- 继续把 Markdown 正则目录作为主要层级来源；
- 仅在 metadata 保存层级，却不让层级参与 embedding 或重排；
- 为降低 chunk 数而牺牲表头、代码围栏和 section 边界；
- 在没有检索 A/B 的情况下全量替换生产索引。

## 11. 风险与待解决问题

- 钉钉完整 JSONML 可能超过网关限制，需要分页或 blocks fallback；
- 原生 block 转 Markdown 时仍需验证复杂嵌套表格、附件、公式和图片说明；
- 路径和目录重复进入每个投影会增加存储量，并可能放大通用词权重，需要 A/B 验证字段模板；
- 无 heading 文档的 `section_path` 只能回退到文档名，后续可探索视觉标题或 block 语义分段，但不能伪装成原生结构；
- 历史生产 chunk 版本不一致，需要迁移清单和重建状态；
- 当前服务器下载脚本存在凭证硬编码风险，应迁移到环境配置并轮换凭证，避免进入仓库和调研产物。

## 12. 下一步

1. 完成三种策略的本地检索 A/B，并按内容型、层级型问题分别统计；
2. 为 token 上限、路径覆盖、代码围栏和表头重复增加自动测试；
3. 人工审核 AGV、ROS、仿真 HTTP 等典型切块的 before/after；
4. 扩展真实 query 集和 canary 文档集；
5. 设计 v3 索引表、版本字段和命中后 context 展开接口；
6. canary 验证通过后再制定全量重建和回滚方案。

## 13. 调研产物

- `sample_manifest.json`：六篇样本及文件夹路径；
- `samples/raw/`：服务器 Markdown 原文；
- `samples/native-download/`：钉钉 Markdown、JSONML、outline 和 blocks；
- `results/current_pipeline_audit.md`：当前 v2 重放结果；
- `results/dingtalk_style_candidate.md`：v3 候选切块统计；
- `results/candidate_chunks/`：逐篇候选上下文块和检索投影；
- `analyze_current_pipeline.py`：v2 审计脚本；
- `dingtalk_style_candidate.py`：v3 离线候选实现；
- `sample_queries.json`：待执行的首轮检索 A/B 查询集。
