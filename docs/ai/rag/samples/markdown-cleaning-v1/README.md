# Markdown 清洗 v1 样本对照

本目录用于人工比较清洗前后的 Markdown，不参与正式知识库入库。

| 样本 | 下载稿 | 清洗稿 | 逐行差异 | 字符缩减 |
| --- | --- | --- | --- | ---: |
| CAN 表格协议 | [原文](./original/01-can-protocol.md) | [清洗版](./cleaned/01-can-protocol.md) | [diff](./diff/01-can-protocol.diff) | 18.06% |
| Setup 操作指南 | [原文](./original/02-setup-guide.md) | [清洗版](./cleaned/02-setup-guide.md) | [diff](./diff/02-setup-guide.diff) | 7.95% |
| 问题排查/接口说明 | [原文](./original/03-troubleshooting.md) | [清洗版](./cleaned/03-troubleshooting.md) | [diff](./diff/03-troubleshooting.diff) | 28.38% |
| 项目复盘 | [原文](./original/04-project-review.md) | [清洗版](./cleaned/04-project-review.md) | [diff](./diff/04-project-review.diff) | 32.51% |
| 会议纪要 | [原文](./original/05-meeting.md) | [清洗版](./cleaned/05-meeting.md) | [diff](./diff/05-meeting.diff) | 7.62% |

问题排查文档缩减最多的主要原因是 13 个图片长 URL 被替换为
`【图片：URL 路径中的真实文件名】`；项目复盘的主要缩减来自样式标签、HTML 列表和导出容器。

清洗规则及工作状态见
[RAG v2：Chunker 与 Leaf 工作记录](../../RAG-v2-02-Chunker.md)。

重新生成清洗稿：

```bash
cd management-system
python docs/ai/rag/samples/markdown-cleaning-v1/build_samples.py
```

生成后的结构统计保存在 [comparison.json](./comparison.json)。
