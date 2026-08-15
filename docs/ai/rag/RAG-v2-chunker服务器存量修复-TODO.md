# RAG v2 Chunker 服务器存量修复 TODO

> 状态：待执行，未授权写库
> 目标：使用已修复的 Chunker 定向修复污染的存量 chunks 和对应 vectors
> 边界：不重建 outline，不全量 rechunk，不修改 Cleaner

## 1. 执行前条件

- [ ] Chunker 修复已提交并部署到执行 rechunk 的版本。
- [ ] 记录服务器代码 commit、数据库路径/实例和执行时间。
- [ ] 确认现有 rechunk/embedding 入口和事务边界，不另写一套未经验证的写库逻辑。
- [ ] 对数据库做可恢复备份，并记录备份位置和恢复命令。
- [ ] 写库、删除旧 chunks 和生成 vectors 前再获得人工确认。

## 2. 只读生成修复清单

输出固定的 `node_id` 清单，每行记录命中原因，清单生成后不再临时扩大范围。

- [ ] A 类：有非空 `content` 但没有有效 leaf 的文档。
- [ ] B 类：存在 `token_count > 512` leaf 的文档。
- [ ] C 类：20 篇 canary 中已确认 baseline/candidate 不同的文档。
- [ ] 对 A/B/C 取并集并去重，保存 `node_id`、`workspace_id`、命中原因、原 leaf 数、最大 token 数。
- [ ] 单独统计 `doc_id IS NULL OR doc_id=''` 的孤儿 chunk，不尝试根据正文猜测它们属于哪篇文档。

已知 baseline 数字仅用于校验口径：

- 空 `doc_id` leaf：2663；
- 有正文但无 leaf 文档：1048；
- 超过 512 token leaf：564，涉及 298 篇文档；
- 当时最大 leaf：12048 token。

如重新统计与上述数字明显不同，先解释差异，不直接写库。

## 3. 写库前 dry-run

- [ ] 使用服务器真实 `content` 和现有 `outline` 运行新 Chunker，但不写数据库。
- [ ] 确认每篇非空文档至少有一个 leaf。
- [ ] 确认所有 leaf `doc_id` 正确、`chunk_index` 连续、`token_count <= 512`。
- [ ] 记录每篇新旧 leaf 数、最大 token 数和内容首尾 marker。
- [ ] 对 leaf 数超过旧版 3 倍或内容召回低于 0.98 的文档人工复核。
- [ ] 输出 dry-run 报告和最终 `node_id` 清单，由人工批准后才进入下一阶段。

## 4. 定向 rechunk 和 embedding

- [ ] 按 50～100 篇一批执行，先用 20 篇 canary 作为首批。
- [ ] 每篇文档使用单独事务：读原文 → 生成新 chunks → 替换该 `node_id` 的旧 chunks → 提交。
- [ ] 不更改 `kb_documents.content` 和 `kb_documents.outline`。
- [ ] 只删除和重建清单内文档对应的 vectors，不全量 embedding。
- [ ] 单篇失败时回滚该文档，记录 `node_id` 和错误，不影响已完成批次。
- [ ] 每批后校验 chunks 数、vectors 数、空 `doc_id`、超限 leaf 和无 leaf 文档数，异常立即停止。

## 5. 孤儿 chunk 处理

- [ ] 先完成 A 类文档重建，确认它们已经有正确 `doc_id` 的 leaf。
- [ ] 备份后单独导出空 `doc_id` 孤儿 chunk 的 ID 清单。
- [ ] 不尝试修改孤儿 chunk 的 `doc_id`；在明确批准后删除孤儿 chunks 及其 vectors。
- [ ] 删除后校验检索和文档页面，确认没有引用断裂。

## 6. 验收

- [ ] 清单内所有非空文档都有有效 leaf。
- [ ] 清单内所有 leaf `token_count <= 512`。
- [ ] 空 `doc_id` leaf 为 0，或每个保留项都有明确豁免说明。
- [ ] chunks 与 vectors 数量、关联关系一致。
- [ ] 20 篇 canary 指标不低于 candidate 报告。
- [ ] 对普通文档、结构化文档、表格和会议纪要各做至少 2 条检索冒烟验证。
- [ ] 记录成功数、失败 `node_id`、数量差异、执行时间和回滚方式。

## 7. 停止条件

出现任一情况立即停止后续批次，保留日志并回滚当前文档：

- 任一新 leaf 超过 512 token；
- 非空文档生成 0 leaf；
- chunks 已替换但 vectors 未成功重建；
- 大量文档的 leaf 数异常增长；
- canary 检索结果明显退化；
- 执行代码 commit 或数据库实例与 dry-run 记录不一致。
