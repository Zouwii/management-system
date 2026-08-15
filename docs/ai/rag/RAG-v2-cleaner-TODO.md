# RAG v2 Cleaner TODO

> 状态：待执行
> 创建：2026-08-10
> 执行范围：只修改 cleaner、审计工具和 cleaner 测试
> 依据：[Cleaner 数据驱动迭代](./RAG-v2-cleaner数据驱动迭代.md)

## 1. 任务目标

修复 100 篇文档审计中确认的 Cleaner 语义问题，并建立可重复执行的 100 篇 canary 审计工具。

本任务完成后，只证明：

- 原始 Markdown 能稳定生成保真的 `kb_documents.content`；
- Cleaner 修改可以通过固定样本进行 baseline/candidate 对照；
- 已确认的 Cleaner Bad Case 已被回归测试覆盖。

本任务不负责证明 outline、chunk 或检索质量。

## 2. 修改范围

允许修改或新增：

```text
backend/ai/knowledge/cleaner.py
backend/tests/test_kb_markdown_cleaner.py
backend/scripts/audit_kb_cleaner.py             # 新增
docs/ai/rag/samples/markdown-cleaner-audit-v2/  # 新增
docs/ai/rag/RAG-v2-cleaner数据驱动迭代.md        # 补充实测结果
```

除非测试无法完成，不修改：

```text
backend/ai/knowledge/routes.py
backend/ai/knowledge/routes_v3.py
backend/ai/knowledge/chunker.py
backend/ai/knowledge/retriever.py
backend/ai/knowledge/embedder.py
数据库 schema
线上 kb_documents / kb_chunks / vectors
```

## 3. 禁止事项

- 不执行线上文档重建、重新切块或重新 embedding。
- 不修改 outline 提取规则。
- 不修改 chunk 大小和表格切分策略。
- 不对所有反斜杠执行全局删除。
- 不把所有相邻 `<span>` 简单拼接，也不统一加空格。
- 不根据字符缩减比例直接判定清洗失败。
- 不删除原文中未知 HTML 的可见文本。
- 不在没有测试的情况下替换成全量 AST 实现。
- 不提交密码、服务器地址对应的凭据或原始业务文档。

## 4. 执行顺序

必须按以下顺序执行。每个任务完成后先运行相关测试，再进入下一项。

## 5. TODO-01：固化 Cleaner 审计工具

### 目的

把一次性 100 篇审计变成可重复运行的工具，后续所有 Cleaner 修改都用同一口径对照。

### 实现

新增：

```text
backend/scripts/audit_kb_cleaner.py
docs/ai/rag/samples/markdown-cleaner-audit-v2/manifest.json
```

审计工具要求：

- 数据库连接必须复用项目配置，禁止硬编码账号密码；
- Markdown 根目录通过命令行参数传入；
- manifest 保存固定 `node_id`、`workspace_id`、标题、样本分类和 baseline content hash；
- 100 篇样本的正文 hash 必须互不重复；
- 原文路径不能写死，按 node/document 元数据解析，并允许文件名 fallback；
- 找不到原文、原文重放与 DB 不一致时明确失败，不能静默跳过；
- 支持输出 JSON 报告；
- 审计过程只读，不更新数据库；
- 返回码必须能被 CI 或 shell 判断。

命令建议：

```bash
cd management-system/backend
.venv/bin/python scripts/audit_kb_cleaner.py \
  --manifest ../docs/ai/rag/samples/markdown-cleaner-audit-v2/manifest.json \
  --markdown-root /home/jz/zhr/markdown \
  --output /tmp/cleaner-audit.json
```

至少输出以下指标：

```text
sample_count
unique_content_count
source_replay_match_count
idempotent_count
table_line_preserved_count
image_reference_preserved_count
code_block_exact_count
lexical_recall_min/median
warning_count
issue_counts
failed_cases[]
```

### 验收

- [ ] manifest 包含 100 篇不同正文。
- [ ] 覆盖短、中、长、超长、表格、图片、代码、转义和固定 Bad Case。
- [ ] 连续运行两次得到相同结果。
- [ ] 工具不修改数据库和原始文件。
- [ ] baseline 与专项文档中的统计一致，或记录差异原因。

## 6. TODO-02：修复相邻 span 拆词

### 已知 Bad Case

```html
<span>p</span><span>rotoc</span>
<span>insta</span><span>nt</span>
<span>energy</span><span>Mode</span>
```

当前可能输出：

```text
p rotoc
insta nt
energy Mode
```

期望：

```text
protoc
instant
energyMode
```

同时必须保留原规则要解决的边界：

```html
<span>上高压</span><span>Bit2 驻车反馈</span>
```

期望不能变成：

```text
上高压Bit2 驻车反馈
```

### 实现要求

- 根据左右字符、原始空白和标点判断连接方式；
- 英文/数字标识符被样式 span 拆分时优先无空格拼接；
- 原文 span 之间存在空白时保留空白；
- 中文与英文、两个独立强调短语之间是否加空格必须有明确规则；
- 表格内外行为都要测试；
- 不通过维护技术词白名单解决。

### 必加测试

- [ ] `p + rotoc → protoc`
- [ ] `insta + nt → instant`
- [ ] `energy + Mode → energyMode`
- [ ] 原本带空格的 span 保留空格
- [ ] `上高压` 与 `Bit2 驻车反馈` 不粘连
- [ ] 表格单元格中的标识符不拆词
- [ ] 修改后仍幂等

## 7. TODO-03：区分图片与钉钉文档链接

### 已知 Bad Case

```markdown
![tb迁移](https://alidocs.dingtalk.com/i/nodes/...)
![tb前后端部署](https://alidocs.dingtalk.com/i/nodes/...)
![scan-safer测试文档](https://alidocs.dingtalk.com/i/nodes/...)
```

这些 URL 指向钉钉文档节点，不是图片资源。当前逻辑会丢失有意义的 alt。

### 实现要求

分类规则至少支持：

| 类型 | 处理 |
|---|---|
| `.png/.jpg/.jpeg/.gif/.webp/.svg` 等图片 URL | 输出图片占位符，保留可用 alt 或文件名 |
| 钉钉 `/i/nodes/` URL | 输出普通 Markdown 链接，保留 alt 和 URL |
| 无扩展名但明确属于图片 CDN | 作为图片，并记录来源 |
| 无法判断 | 保留原 Markdown，增加 warning |

图片占位符优先级：

1. 有意义的 alt；
2. URL 中真实图片文件名；
3. `【图片】`。

`image.png`、空 alt、纯 UUID 文件名可视为低价值 alt，但不能误删业务标题。

### 必加测试

- [ ] 钉钉 node URL 保留 `tb迁移`。
- [ ] 普通 PNG URL 转换为一个图片占位符。
- [ ] 有意义 alt 优先于 UUID 文件名。
- [ ] 空 alt 使用图片文件名。
- [ ] 无法分类的 URL 保留原文并产生 warning。
- [ ] 一次输入只产生一个对应引用，不重复。
- [ ] 修改后仍幂等。

## 8. TODO-04：恢复整篇转义 Markdown

### 已知 Bad Case

```text
\# JState 错误码 614002：地图异常
\## 1 错误结论
\| 字段 \| 内容 \|
\|---\|---\|
```

### 实现要求

- 只在“结构性转义占主导”时启用整篇恢复；
- fenced code 内不反转义；
- 普通文本、Shell、正则、公式中的合法 `\#`、`\|` 不改变；
- 恢复后必须形成合法、连续的 Markdown 标题或表格结构；
- 低置信度时保持原文并产生 warning；
- 在 `CleanResult.stats` 中记录是否执行结构恢复及恢复数量。

推荐判定条件组合，而不是单条正则：

```text
正常标题数量 == 0
且 escaped heading 数量 >= 阈值

或

正常表格行数量 == 0
且存在连续多行 escaped table
```

### 必加测试

- [ ] 整篇 `\#` 标题恢复。
- [ ] 连续 `\|...\|` 表格恢复。
- [ ] fenced code 内的 `\#`、`\|` 不变化。
- [ ] Shell 管道转义不变化。
- [ ] 正则表达式中的反斜杠不变化。
- [ ] 只有一行局部 escaped heading 时不触发整篇恢复。
- [ ] 修改后仍幂等。

## 9. TODO-05：明确 fenced code 保真契约

### 已知现象

Cleaner 在保护 code block 前执行 `_normalize_basic()`，其中 NBSP 会变成普通空格。因此当前“代码块不清洗”并非严格成立。

### 决策

本任务采用严格保真：

> 除换行符统一为 `\n` 外，fenced code 的 fence、语言、内容和空白保持不变。

### 实现要求

- 调整保护与基础规范化顺序；
- BOM 和 CRLF 处理不能破坏 fenced code 边界识别；
- 未闭合 code fence 原样保留并产生 warning；
- 不改写 code block 内 HTML、图片语法、span、NBSP 和转义字符。

### 必加测试

- [ ] code block 内 NBSP 保留。
- [ ] code block 内 HTML 保留。
- [ ] code block 内图片语法不转占位符。
- [ ] code block 内 escaped Markdown 不反转义。
- [ ] 未闭合 fence 原样保留并 warning。
- [ ] CRLF 输入规范化后 fence 仍正确闭合。

## 10. TODO-06：补充审计元数据

### 实现

扩展 `CleanResult.stats`，至少增加：

```text
input_chars
output_chars
heading_count
table_line_count
code_block_count
image_count
document_link_count
unknown_media_count
escaped_heading_restored_count
escaped_table_restored_count
span_join_count
span_space_count
warning_count
```

warning 使用稳定代码，不在 warning 字符串中混入不可解析的自由文本。建议：

```text
UNCLOSED_CODE_FENCE
UNKNOWN_HTML_TAG:<tag>
UNKNOWN_MEDIA_URL
AMBIGUOUS_ESCAPED_MARKDOWN
```

### 验收

- [ ] stats 字段有单元测试。
- [ ] 同一输入重复运行 stats 一致。
- [ ] 审计工具能够汇总 stats 和 warnings。

## 11. TODO-07：运行完整验证

### 单元测试

```bash
cd management-system/backend
.venv/bin/python -m unittest tests.test_kb_markdown_cleaner
```

如果仓库使用 pytest，也运行：

```bash
cd management-system/backend
.venv/bin/python -m pytest tests/test_kb_markdown_cleaner.py -q
```

### 100 篇 canary

运行 TODO-01 建立的审计命令，保存 candidate 报告。

### 人工 diff

至少检查以下类型各 2 篇，总计不少于 10 篇：

- span 密集技术文档；
- 图片/链接密集文档；
- 整篇或局部转义文档；
- fenced code 密集文档；
- 长表格文档。

### 最终验收门槛

- [ ] 原有 Cleaner 测试全部通过。
- [ ] 新增 Bad Case 测试全部通过。
- [ ] 100/100 样本可重放。
- [ ] 100/100 幂等。
- [ ] 表格行非预期丢失为 0。
- [ ] 图片/文档链接类型误判为 0。
- [ ] fenced code 非预期变化为 0。
- [ ] 已确认 span 拆词为 0。
- [ ] 整篇转义 Bad Case 恢复成功。
- [ ] 局部合法转义没有被批量修改。
- [ ] candidate 没有新增高严重度 Bad Case。
- [ ] `git diff --check` 通过。

## 12. TODO-08：更新文档并提交执行报告

更新：

```text
docs/ai/rag/RAG-v2-cleaner数据驱动迭代.md
```

执行报告必须包含：

```text
修改文件
规则变更摘要
新增测试清单
测试命令与结果
100 篇 baseline/candidate 对照
未解决 Bad Case
受影响文档估算
是否建议进入文档重建阶段
```

本任务结束时不要执行线上重建。由人工审核 diff 和报告后，再单独创建重建任务。

## 13. 后续任务，不在本 TODO 内

Cleaner 验收后，另建任务依次处理：

1. 保存 raw content、cleaner version 和 checksum；
2. 修复 outline：代码块标题、粗体标题、数字标题、末尾数字和纯表格根节点；
3. 重建受影响 documents 的 content 和 outline；
4. 再分析 302 篇低 chunk 覆盖率文档；
5. 最后决定是否重建 chunks 和 vectors。
