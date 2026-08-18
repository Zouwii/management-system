# RAG v2 文档索引

> 更新：2026-08-18
> 当前阶段：Cleaner 已冻结，Chunker 优化暂停，现有 leaf 检索与问答链路可用；parent 仅保留为后续上下文扩展能力

## 1. 工作顺序

| 顺序 | 文档 | 状态 | 作用 |
|------|------|------|------|
| 01 | [Cleaner](./RAG-v2-01-Cleaner.md) | 已完成并冻结 | 记录 Markdown 清洗规则、真实样本审计和保真结论 |
| 02 | [Chunker](./RAG-v2-02-Chunker.md) | 暂停优化、现有数据可用 | 记录切分演进、服务器修复、leaf-only 清理、BGE token 与结构问题 |
| 03 | [知识助手设计](./RAG-v2-03-知识助手设计.md) | 设计参考 | 定义目标用户、产品范围和结构化查询 + RAG 总体方向 |
| 04 | [多模态扩展](./RAG-v2-04-多模态扩展.md) | 暂缓 | 保存图片、OCR 和多模态检索的扩展设计，不属于当前实施范围 |

当前执行以 01、02 的实测记录为准。当前架构是“leaf-only 初始召回与向量 + parent/sibling 上下文扩展”；03、04 中的自动同步和多模态内容仍只作为设计背景。

## 2. 当前结论

- `kb_documents.content` 是 Cleaner 后 Markdown 的正文源；
- Cleaner 已通过现有审计，除非真实检索 Bad Case 指向 Cleaner，否则不继续调整；
- 数据库当前只有 35,076 个有效 leaf 和对应 vector，尚未生成 parent；这不影响现有检索，parent 只在后续上下文不足时按需启用；
- 未启用且为空的 `kb_documents_v2`、`kb_blocks`、`kb_assets`、`kb_chunks_v2` 已备份 DDL 后删除；
- Parent 生成、精确 child 映射、共享写库、leaf-only embedding 和 leaf-only 初始召回已在代码层修复；
- 当前主要问题是 Chunker 使用的 token 计数与 BGE tokenizer 不一致，以及超长表格、代码块的跨 leaf 结构保真；
- 查询侧 BGE 模型已在服务器启用，关键词、向量和 Hybrid 检索均已实测返回结果；
- Reranker 的 FlagEmbedding 参数已由错误的 `device` 修正为 `devices`，完整 SSE 问答已返回引用、正文和 `done`；
- SSE 子窗口已与终端 Agent Skill 解耦，不再向模型注入 curl 和工具调用说明；
- 自动同步、全量重建和多模态暂不优先。

完整数据、备份和 2026-08-18 操作记录见 [Chunker 第 13 节](./RAG-v2-02-Chunker.md#13-leaf-only-清理与-chunker-现状复核2026-08-18)。

## 3. 文档管理规则

1. 文件名前缀 `RAG-v2-XX-` 表示稳定工作顺序，不表示完成百分比。
2. 不再创建独立 `TODO` 文档；待处理事项写入对应长期文档的“下一步”章节。
3. 已执行的数据修复、审计结果和设计决策按日期追加，保留历史上下文。
4. 当前状态优先看本索引和对应文档最新日期的章节，不能只读取早期设计段落。
5. 样例、diff 和 JSON 报告继续放在 `samples/`，不参与正式文档编号。

## 4. 下一步

1. 使用真实问题建立现有 leaf-only 检索与问答基线；
2. 记录 Bad Case 属于召回、重排、上下文还是生成；
3. 单独处理模型输出 `<think>` 思考标签的展示问题；
4. 只有真实 Bad Case 指向上下文不足时，才启用 parent/sibling 扩展；
5. BGE token、表格和代码块切分保持暂停，出现对应 Bad Case 后再恢复。
