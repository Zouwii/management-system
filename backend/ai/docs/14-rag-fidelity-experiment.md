# RAG 保真采集与切分实验方案

> 日期: 2026-07-22
> 范围: 单知识库旁路实验，不替换现有 RAG 主链路

## 1. 背景

当前知识库 RAG 链路以文本 MVP 为主：

```text
DingTalk blocks / workbook -> Markdown -> kb_documents.content -> chunker -> kb_chunks.content -> embedding / retrieval
```

这个链路能覆盖普通文本问答，但存在信息保真问题：

- 图片、流程图、截图、附件等非文本信息没有稳定进入索引。
- 当前主同步路径主要处理 `category == ALIDOC`，非 ALIDOC 文档会被跳过。
- `blocks_to_markdown()` 对 DingTalk blocks 中的图片、附件、媒体类 block 没有主路径处理。
- `raw_json` 当前主要保存节点元数据，不保存完整 blocks 原文，后续难以离线补救。
- `kb_chunks` 只保存文本内容，缺少 `heading`、`path`、`chunk_type`、`asset_refs` 等结构化字段。

因此，本实验不优先优化 embedding / reranker，而是先验证“保真采集 + asset-aware chunk”是否能改善知识保留。

## 2. 实验目标

### 2.1 要验证的问题

1. 对一个指定知识库，能否完整保存原始 DingTalk blocks。
2. 能否识别并统计图片、附件、媒体、未知 block。
3. Markdown 降级文本中能否保留图片/附件占位符，而不是静默丢失。
4. chunk 能否携带来源路径、章节、block 范围和 asset 引用。
5. 检索命中 chunk 后，是否能回到原文文档和相关图片/附件位置。

### 2.2 非目标

- 不做全量知识库迁移。
- 不替换现有 `/ai/knowledge/sync-and-embedding`。
- 不做图片多模态理解。
- 不做 OCR。
- 不改现有线上 retriever 排序逻辑。
- 不要求一次性支持 PDF / DOCX 正文解析。

## 3. 实验范围

### 3.1 知识库选择

优先选择一个“小而典型”的知识库：

- 文档数量适中，避免同步成本过高。
- 包含一定数量的图片、表格、流程图或附件。
- 有真实业务问题可以验证检索效果。

建议候选：

| 候选 | 优点 | 风险 |
|------|------|------|
| 单个部门知识库 | 内容贴近业务，容易验证 | 文档可能较多 |
| 一个专项知识库 | 范围较小，适合试验 | 图片/附件样本可能不足 |
| 新建测试知识库 | 可控，样本清晰 | 与真实文档分布可能不同 |

实验参数固定为一个 `workspace_id`。没有显式传入实验 workspace 时，不启用实验链路。

### 3.2 代码范围

新增旁路模块，尽量不修改现有主链路：

```text
backend/ai/knowledge/
├── experimental/
│   ├── __init__.py
│   ├── routes.py             # 实验 API
│   ├── sync.py               # 单知识库保真同步
│   ├── normalizer.py         # DingTalk blocks -> normalized blocks
│   ├── chunker.py            # block-aware chunk
│   └── models.py             # 实验表模型，如需要
```

如果为了减少表迁移，也可以先不建独立 ORM 文件，把实验字段以 JSON 形式存到新表中。

## 4. 推荐方案

### 4.1 旁路表方案

为了降低对线上数据的影响，优先使用实验表：

```text
kb_exp_documents
kb_exp_blocks
kb_exp_assets
kb_exp_chunks
```

好处：

- 不污染现有 `kb_documents` / `kb_chunks`。
- 可随时清空重跑。
- 表结构可以快速迭代。
- 验证完成后再决定是否迁移主表。

### 4.2 最小表结构

#### kb_exp_documents

```sql
CREATE TABLE kb_exp_documents (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    doc_id VARCHAR(128) NOT NULL UNIQUE,
    workspace_id VARCHAR(128) NOT NULL,
    title VARCHAR(512) NOT NULL,
    category VARCHAR(32) DEFAULT '',
    node_type VARCHAR(32) DEFAULT '',
    parent_id VARCHAR(128) DEFAULT '',
    path_text TEXT,
    remote_modified_at DATETIME NULL,
    raw_node_json MEDIUMTEXT,
    raw_blocks_json MEDIUMTEXT,
    markdown MEDIUMTEXT,
    synced_at DATETIME,
    created_at DATETIME,
    updated_at DATETIME
);
```

#### kb_exp_assets

```sql
CREATE TABLE kb_exp_assets (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    doc_id VARCHAR(128) NOT NULL,
    block_id VARCHAR(128) DEFAULT '',
    asset_type VARCHAR(32) NOT NULL,      -- image / attachment / media / unknown
    title VARCHAR(512) DEFAULT '',
    url TEXT,
    raw_json MEDIUMTEXT,
    created_at DATETIME,
    INDEX idx_kb_exp_assets_doc (doc_id)
);
```

#### kb_exp_chunks

```sql
CREATE TABLE kb_exp_chunks (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    doc_id VARCHAR(128) NOT NULL,
    chunk_index INT NOT NULL,
    chunk_type VARCHAR(32) DEFAULT 'text', -- text / table / mixed / asset_context
    heading VARCHAR(512) DEFAULT '',
    path_text TEXT,
    content MEDIUMTEXT NOT NULL,
    token_count INT DEFAULT 0,
    block_start INT DEFAULT NULL,
    block_end INT DEFAULT NULL,
    asset_refs_json TEXT,
    metadata_json TEXT,
    created_at DATETIME,
    INDEX idx_kb_exp_chunks_doc (doc_id, chunk_index)
);
```

### 4.3 normalized block 中间表示

不要直接把 DingTalk blocks 转成 Markdown。先转成中间结构：

```json
{
  "block_id": "xxx",
  "index": 12,
  "type": "image",
  "text": "",
  "heading_level": null,
  "asset": {
    "type": "image",
    "title": "现场截图",
    "url": "https://..."
  },
  "raw": {}
}
```

推荐 block 类型：

| 类型 | 含义 | 降级方式 |
|------|------|----------|
| `heading` | 标题 | `## 标题` |
| `paragraph` | 普通段落 | 原文 |
| `list` | 有序/无序列表 | Markdown list |
| `table` | 表格 | Markdown table 或压缩行 |
| `code` | 代码块 | fenced code |
| `image` | 图片 | `[图片: title]` |
| `attachment` | 附件 | `[附件: title]` |
| `media` | 视频/音频 | `[媒体: title]` |
| `unknown` | 未识别 block | `[未知内容: blockType=xxx]` |

## 5. 实验 API

新增实验入口，避免影响旧接口：

```text
POST /api/bt/ai/knowledge/experimental/sync
POST /api/bt/ai/knowledge/experimental/rechunk
POST /api/bt/ai/knowledge/experimental/search
GET  /api/bt/ai/knowledge/experimental/documents/<doc_id>
```

### 5.1 sync

请求：

```json
{
  "workspace_id": "xxx",
  "limit": 20,
  "check_modified": false
}
```

行为：

1. 只遍历指定 `workspace_id`。
2. 拉取节点元数据。
3. 对 ALIDOC 拉取完整 blocks。
4. 保存 `raw_blocks_json`。
5. 生成 normalized blocks。
6. 保存 assets。
7. 生成降级 Markdown。

返回：

```json
{
  "synced_docs": 20,
  "asset_count": 15,
  "image_count": 10,
  "attachment_count": 3,
  "unknown_block_count": 2,
  "failed_count": 0
}
```

### 5.2 rechunk

请求：

```json
{
  "workspace_id": "xxx",
  "doc_id": "",
  "all": true
}
```

行为：

1. 从 `kb_exp_documents.raw_blocks_json` 或 normalized blocks 重建 chunk。
2. chunk 中保留 `heading`、`path_text`、`block_start`、`block_end`。
3. 如果 chunk 范围内包含图片/附件，写入 `asset_refs_json`。

### 5.3 search

第一版可以只做关键词搜索，不接 embedding：

```json
{
  "q": "急停流程图",
  "workspace_id": "xxx",
  "top_k": 10
}
```

返回 chunk 时带 asset 引用：

```json
{
  "chunk_id": 123,
  "doc_id": "xxx",
  "title": "急停设计说明",
  "heading": "3.2 急停流程",
  "content": "... [图片: 急停状态机图] ...",
  "assets": [
    {"type": "image", "title": "急停状态机图", "url": "..."}
  ]
}
```

## 6. Chunk 策略调整

实验 chunker 不再只面对 Markdown 字符串，而是面对 normalized blocks。

### 6.1 切分原则

- 标题块决定章节边界。
- 图片/附件不单独丢弃，归属到最近的前文段落或章节。
- 表格作为独立 chunk 类型处理。
- 大段文本仍按 token 窗口切。
- 每个 chunk 都保存 block index 范围。

### 6.2 图片处理策略

第一阶段只做“可见性保留”：

```text
[图片: 急停状态机图]
```

如果没有标题：

```text
[图片: doc_id=xxx block_index=12]
```

后续可扩展：

- 下载图片并缓存。
- OCR 识别图片中文字。
- 使用多模态模型生成图片描述。
- 图片描述进入 chunk content，原图作为 asset 引用。

## 7. 验收指标

### 7.1 数据保真指标

| 指标 | 目标 |
|------|------|
| raw blocks 保存率 | 100% |
| ALIDOC 文档同步成功率 | >= 95% |
| 图片 block 识别率 | 能统计，先不设准确率 |
| 附件 block 识别率 | 能统计，先不设准确率 |
| unknown block 统计 | 必须输出 |
| chunk asset 引用 | 命中图片/附件所在章节时可返回 |

### 7.2 检索验证样本

人工选 10 篇文档：

- 3 篇图片/流程图较多。
- 3 篇表格较多。
- 2 篇普通结构化设计文档。
- 2 篇带附件或未知 block。

每篇准备 1-2 个问题，验证：

1. 旧 RAG 是否丢信息。
2. 实验 RAG 是否至少能提示“原文此处有图片/附件”。
3. chunk 是否能定位到正确章节。
4. 返回引用是否包含 doc_id、heading、asset_refs。

## 8. 实施步骤

### Step 1: 选定 workspace

确认实验 `workspace_id`，限定同步范围。

输出：

- workspace 名称
- workspace_id
- 预计文档数量
- 样本文档列表

### Step 2: 建实验表

新增迁移脚本，例如：

```text
backend/scripts/migrate_kb_exp_storage.sql
```

只创建 `kb_exp_*` 表，不改旧表。

### Step 3: 保真同步

新增 experimental sync：

- 拉节点。
- 拉 blocks。
- 保存 raw blocks。
- 生成 markdown 降级文本。
- 保存 assets。
- 输出 block 类型统计。

### Step 4: block-aware rechunk

从 normalized blocks 切 chunk：

- heading-aware
- table-aware
- asset-aware
- 保存 block range 和 asset refs

### Step 5: 关键词搜索验证

先不接向量，直接对 `kb_exp_chunks.content` 做关键词检索或 LIKE 验证。

### Step 6: 小规模评估

用 10-20 个问题比较旧链路和实验链路。

输出一份对照表：

| 问题 | 旧链路结果 | 实验链路结果 | 是否改善 | 备注 |
|------|------------|--------------|----------|------|

## 9. 风险与回滚

| 风险 | 处理 |
|------|------|
| 钉钉 blocks 图片字段不稳定 | 先保存 raw blocks，再逐步补 parser |
| API 调用量增加 | limit + 单 workspace + 手动触发 |
| 表结构需要频繁调整 | 使用 `kb_exp_*` 旁路表，可清空重建 |
| 图片 URL 有权限/过期问题 | 第一阶段只保存引用，不保证长期可访问 |
| 检索效果暂时无提升 | 本实验先验证保真，不以回答质量作为唯一指标 |

回滚方式：

1. 停止调用 experimental API。
2. 删除或清空 `kb_exp_*` 表。
3. 现有 `kb_documents`、`kb_chunks`、retriever 不受影响。

## 10. 后续迁移判断

满足以下条件后，再考虑合并进主链路：

- 实验 workspace 中 raw blocks 和 asset 统计稳定。
- 图片/附件不会再静默丢失。
- chunk 能返回 `heading/path/asset_refs`。
- 至少 10 个验证问题中，实验链路的信息定位优于旧链路。
- 同步耗时和 API 调用量可接受。

迁移时优先采用渐进方式：

1. 给主表增加 `raw_blocks_json` / `metadata_json` / `asset_refs_json`。
2. 主同步保存 raw blocks。
3. 主 chunker 改为 block-aware。
4. retriever 返回结构化引用。
5. 最后再考虑 OCR / 多模态图片描述。
