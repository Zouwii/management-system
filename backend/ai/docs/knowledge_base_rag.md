# 知识库 RAG 系统设计

> 最后更新: 2026-05-26

## 1. 目标与场景

将钉钉知识库内容接入 AI 系统，支持两个场景：

1. **知识库对话** — 用户与 AI 自由对话，AI 基于知识库内容回答
2. **AI 任务分析** — 分析任务时自动引用知识库规范文档

### 1.1 非目标（当前阶段）

- 知识库文档的在线编辑/管理
- 多模态内容理解（图片降级处理）
- 知识库权限与钉钉侧的实时同步
- 对话历史持久化存储（内存缓存，TTL 30min）

---

## 2. 已完成：Phase 1 — 文档浏览与下载服务

### 2.1 成果

实现了钉钉知识库的完整浏览和下载管线：

```
用户 → Flask API → DingTalkKnowledgeClient → 钉钉 API
                       ↓
                  parser.py (blocks/HTML/workbook → Markdown)
                       ↓
                  SQLite (kb_documents)
```

### 2.2 API 端点

| 端点 | 方法 | 功能 |
|------|------|------|
| `/ai/knowledge/workspaces` | GET | 列出知识库（按优先级排序，10个已知库） |
| `/ai/knowledge/workspaces/<id>/nodes` | GET | 浏览文档目录树 |
| `/ai/knowledge/documents/<node_id>` | GET | 获取文档内容（cache-first, then API） |
| `/ai/knowledge/sync` | POST | 遍历知识库树，缓存所有文档 |
| `/ai/knowledge/search` | POST | 全文搜索（全局/指定知识库） |

### 2.3 已验证的钉钉 API

| API | 方法 | 用途 |
|-----|------|------|
| `/v2.0/wiki/workspaces` | GET | 知识库列表 |
| `/v2.0/wiki/nodes` | GET | 节点目录（parentNodeId 参数） |
| `/v2.0/wiki/nodes/<id>` | GET | 节点元数据 |
| `/v1.0/doc/suites/documents/<id>/blocks` | GET | 文档 blocks（主要格式） |
| `/v1.0/doc/workbooks/<id>/sheets` | GET | 表格 sheet 列表 |
| `/v1.0/doc/workbooks/<id>/sheets/<s>/ranges/<r>` | GET | 表格单元格数据 |
| `/v2.0/storage/dentries/search` | POST | 全局搜索 |
| `/v1.0/doc/docs` | GET | 知识库内搜索 |

认证：App-level `access_token`，通过 `x-acs-dingtalk-access-token` header 传递。

### 2.4 知识库优先级

```python
KNOWN_WORKSPACES = {
    "1oam4Sk7BMLXxn8K": 0,   # 本体开发部
    "By8jQSbJyWLAL30M": 1,   # 研发共享文档
    "yq8ZkS3KYJW4enaX": 2,   # 研发体系文档【JZ-TOTAL】
    "9Bv51SJGoKxPBjv3": 3,   # 研发体系全员文档库
    "X1v4RS7ybR4GeZ8P": 4,   # 研发共享文档（非公开）
    "5zaVASrJnl5bDo8y": 5,   # 产品专项知识库
    "9Bv51SWzXGOJOzv3": 6,   # 研发专项知识库
    "bJvOOSLN3yLzGgvK": 7,   # 订单专项知识库
    "OQ0xySKEGYKEG48B": 8,   # 产品信息门户
    "MJ0pDSwlOEkMqQ0E": 9,   # 订单项目信息门户
}
```

### 2.5 文档解析器

支持三种输入格式 → Markdown：

| 输入格式 | 来源 | 处理方式 |
|---------|------|---------|
| DingTalk blocks | `/v1.0/doc/.../blocks` API | `blocks_to_markdown()` 递归转换 |
| Workbook | `/v1.0/doc/workbooks/...` API | `workbook_to_markdown()` 表格转换 |
| HTML/JSON | fallback | 正则清洗 + block tree 递归 |

### 2.6 数据模型（已建表）

- **kb_documents** — 文档主表（doc_id, workspace_id, title, content, node_type, parent_id, raw_json, synced_at）
- **kb_chunks** — 分片表（doc_id, chunk_index, content, token_count），预留
- **kb_chunks_fts** — FTS5 全文索引虚拟表，预留

### 2.7 "本体开发部" 知识库结构

已完整遍历，关键特征：

- **9 个顶级目录**，3-5 层深度嵌套
- **主力格式** `.adoc`（钉钉文档），少量 `.axls`（表格）、`.docx`、`.pdf`
- **内容类型**：技术设计文档、会议纪要、代码评审、项目需求、周报、规范制度
- **文档粒度小**：大量独立小文档，天然适合按文档切片

---

## 3. Phase 2：文档切片策略

### 3.1 设计原则

1. **语义完整** — 每个切片是一个自包含的语义单元，LLM 拿到后不需要上下文也能理解
2. **类型感知** — 不同文档类型用不同策略，不一刀切
3. **元数据注入** — 每个切片带文档来源路径和章节信息，支持引用标注
4. **token 精确** — 用 `tiktoken` 计数，避免超长切片撑爆 prompt

### 3.2 切片规则

#### 类型一：规范/设计文档（层级分明）

适用于有 `##`/`###` 标题结构的文档（占大多数）。

```
策略：标题切分
  - 以 ## 为主要切分点（### 作为辅助，仅当 ## 区间 > 1000 token 时下钻）
  - 目标粒度：800-1000 token
  - 最小阈值：100 token（低于此与上一片合并）
  - 重叠窗口：相邻切片重叠 150 token
  - 每片格式：文档路径 + 章节标题 + 正文
```

切片示例：

```
[来源: 本体开发部/技术三组/订单模块设计规范]
[章节: ## 3.2 支付回调处理]
正文内容...
```

#### 类型二：会议纪要/周报（短段落+列表）

识别方式：标题含"会议纪要"、"周报"、"日报"、"总结"，或目录路径包含"会议"、"周报"。

```
策略：段落聚合
  - 按段落（空行分隔）为基本单元
  - 聚合至每片 ≥ 200 token
  - 目标粒度：500-800 token
  - 无重叠（内容本身重复度高）
```

#### 类型三：表格（.axls / workbook）

```
策略：行分组 + 表头前缀
  - 每 20-30 行为一片
  - 每片前重复表头行
  - 格式：sheet 名称 + 列名 + 数据行
```

#### 类型四：其他（纯文本、代码片段等）

```
策略：固定窗口
  - 按 800 token 固定窗口滑动
  - 150 token 重叠
```

### 3.3 文档类型识别

```python
def classify_document(title: str, path: str, content: str) -> str:
    """返回: 'structured' | 'meeting' | 'table' | 'text'"""
    # 1. 表格优先（node_type == "WORKBOOK"）
    # 2. 会议纪要：标题/路径关键词
    # 3. 规范文档：content 中有 ## 层级结构
    # 4. 其余：按固定窗口处理
```

### 3.4 切片元数据

每个切片携带的元数据结构：

```python
@dataclass
class ChunkMeta:
    doc_id: str           # 源文档 ID
    doc_title: str        # 文档标题
    workspace_name: str   # 所属知识库名称
    path: str             # 知识库内路径（目录层级）
    chunk_index: int      # 切片序号
    heading: str          # 最近的上层标题（如 "## 3.2 支付回调"）
    token_count: int      # 实际 token 数
```

路径示例：`本体开发部 > 技术三组 > 订单项目 > 2025 > 模块设计 > 支付模块设计`

### 3.5 Token 计算

使用 `tiktoken` 库，编码器 `cl100k_base`（与 text-embedding-3-small 一致）：

```python
import tiktoken
encoder = tiktoken.get_encoding("cl100k_base")

def count_tokens(text: str) -> int:
    return len(encoder.encode(text))
```

中文实际比例约 1 汉字 ≈ 1.5-2 tokens。

### 3.6 切片存储

切片写入 `kb_chunks` 表，同时更新 FTS5 索引：

```sql
-- 切片时：INSERT INTO kb_chunks (doc_id, chunk_index, content, token_count)
-- 全文索引自动同步（content=kb_chunks 的外部内容表模式）
INSERT INTO kb_chunks_fts(kb_chunks_fts) VALUES ('rebuild');
```

### 3.7 重新切片策略

- 文档内容更新 → 删除该文档的所有旧切片 → 重新切片
- 切片规则调整 → 提供 `POST /ai/knowledge/rechunk` 全量重建接口

---

## 4. Phase 3：向量化与混合检索

### 4.1 Embedding

通过 One-API 网关调用 embedding 模型：

```
POST {one-api-base}/v1/embeddings
{ "model": "text-embedding-3-small", "input": "切片文本..." }
→ { "data": [{ "embedding": [0.123, -0.456, ...] }] }
```

备选：如果 One-API 不支持 embedding，改用 `MiniMax` 或 `step` 平台接口。

### 4.2 向量存储选择

| 方案 | 优势 | 劣势 |
|------|------|------|
| **SQLite + vec0** | 零部署，与现有 SQLite 一致 | 需编译扩展 |
| Chroma | 轻量嵌入式 | 额外依赖 |
| pgvector | 成熟稳定 | 需要 PostgreSQL |

**推荐**：优先尝试 SQLite vec0 扩展，如果不可行则 Docker 部署 pgvector。

如果短期内不想引入向量检索，可以先用 **纯 FTS5 关键词检索** 作为 MVP，效果对于中文技术文档已经可用。

### 4.3 混合检索流程

```
用户问题
    │
    ├──→ Embedding → 向量相似度 top-20
    │
    └──→ 分词 → FTS5 全文索引 top-10
              │
              ▼
        结果合并 + RRF 重排序 → top-8
              │
              ▼
        构造 Prompt → LLM 生成
```

检索参数：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| 向量检索 top-N | 20 | 语义相似度 |
| 全文检索 top-N | 10 | 关键词匹配 |
| 最终 top-K | 8 | RRF 重排序后 |
| 单片段最大 token | 800 | 超长截断 |
| 总召回 token 上限 | 4000 | 控制 prompt 长度 |

### 4.4 检索范围控制

支持按知识库过滤：

```
POST /ai/knowledge/search
{ "keyword": "...", "workspace_id": "1oam4Sk7BMLXxn8K" }
```

聊天检索时默认搜索所有已缓存知识库，按 workspace 优先级排序结果。

---

## 5. Phase 4：知识库对话

### 5.1 交互流程

```
用户发送消息
    ↓
[1] 混合检索（FTS5 + 向量）→ top-8 切片
    ↓
[2] 构造 Prompt:
    System: 知识库引用片段 + 角色设定
    User: 原始问题 + 最近 2 轮历史
    ↓
[3] LLM 生成 → SSE 流式返回
    ↓
[4] 前端展示 + 引用标记
```

### 5.2 SSE 接口

```
GET /ai/knowledge/chat?q=问题&session_id=xxx

event: message
data: {"type": "text", "content": "部分回答..."}

event: message
data: {"type": "citation", "source": "文档标题", "path": "..."}

event: done
data: {"type": "done"}
```

### 5.3 Prompt 结构

```text
你是企业内部知识助手，基于以下知识库内容回答问题。
用中文回答，语言简洁准确。知识库内容不足时请明确告知，不要编造。

知识库内容：
---
[来源：支付模块设计规范（本体开发部/技术三组/订单项目）]
{切片内容...}

[来源：代码评审规范 v2.1（本体开发部/应用工程/规范）]
{切片内容...}
---

用户问题：{问题}
```

### 5.4 多轮对话

- session_id 由前端生成
- 后端内存缓存最近 5 轮对话（TTL 30 分钟）
- 每轮独立检索，不缓存检索结果
- 历史仅用于 LLM 生成上下文

---

## 6. Phase 5：AI 任务分析增强

### 6.1 流程

```
用户选择任务/项目 → 触发分析
    ↓
[1] 拉取任务数据（工时、进度、逾期等）
[2] 根据任务类型 + 项目信息构建检索词 → 检索知识库
[3] 构造分析 Prompt（任务数据 + 规范引用）
[4] LLM 生成分析报告（非流式 JSON）
```

### 6.2 API

```
POST /ai/analyze_task
{ "task_id": "xxx", "project_id": "yyy" }

→ {
    "summary": "任务整体良好，需求描述需补充",
    "risks": ["缺少验收标准"],
    "suggestions": ["参考《需求文档规范》第3节"],
    "evidence": [{ "source": "需求文档规范 v2.3", "content": "..." }]
}
```

---

## 7. 模块结构（目标）

```
backend/ai/knowledge/
├── __init__.py        # register(bp, ok, fail)
├── routes.py          # HTTP 端点（已完成：5 个端点）
├── service.py         # DingTalkKnowledgeClient（已完成）
├── parser.py          # 文档解析（已完成：blocks/html/workbook → MD）
├── models.py          # ORM + FTS5 表（已完成）
├── chunker.py         # 文档切片（待实现）
├── embedder.py        # Embedding 调用（待实现）
├── retriever.py       # 混合检索（待实现）
├── chat.py            # SSE 对话生成（待实现）
└── chat_session.py    # 会话管理（待实现）
```

---

## 8. 实施计划

| 阶段 | 内容 | 预估 |
|------|------|------|
| Phase 1 | 文档浏览与下载 ✅ | 已完成 |
| Phase 2 | 文档切片（chunker.py + 重新切片 API） | 2-3 天 |
| Phase 3 | 向量化 + 混合检索 | 3-5 天 |
| Phase 4 | SSE 知识库对话 | 3-5 天 |
| Phase 5 | 任务分析增强 | 2-3 天 |

---

## 9. 风险与应对

| 风险 | 影响 | 应对 |
|------|------|------|
| 文档解析质量差（表格、图片） | 切片内容不完整 | 表格转 markdown table，图片忽略；降级标记 |
| 切片策略不适合实际检索 | 检索召回率低 | 提供 rechunk 接口快速迭代，用户反馈驱动调整 |
| One-API 不支持 embedding | 无法向量检索 | 先用纯 FTS5 关键词检索做 MVP，后续接 MiniMax/step |
| 检索延迟高 | 对话体验差 | SSE 流式返回，检索阶段控制在 500ms 内 |
| 知识库量大导致噪音 | 回答不准确 | 混合检索 + RRF 重排序，持续调优 |
