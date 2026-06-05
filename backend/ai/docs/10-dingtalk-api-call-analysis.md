# 钉钉 API 调用分析

> 分析日期: 2026-06-04
> 数据来源: `runtime/logs/ai_debug.log` (2026-05-26 ~ 2026-06-03)

---

## 一、涉及的钉钉 API 端点

| # | 钉钉 API | 用途 |
|---|---------|------|
| ① | `GET /v2.0/wiki/workspaces` | 获取知识库列表 |
| ② | `GET /v2.0/wiki/nodes` | 获取目录子节点 |
| ③ | `GET /v2.0/wiki/nodes/<nodeId>` | 获取节点元数据 |
| ④ | `GET /v1.0/doc/suites/documents/<nodeId>/blocks` | 获取文档内容（普通文档） |
| ⑤ | `GET /v1.0/doc/workbooks/<nodeId>/sheets` | 获取表格 Sheet 列表 |
| ⑥ | `GET /v1.0/doc/workbooks/<nodeId>/sheets/<id>/ranges/<range>` | 读取表格单元格数据 |
| ⑦ | `POST /v2.0/storage/dentries/search` | 全局搜索文档 |
| ⑧ | `GET /v1.0/doc/docs` | 知识库内搜索文档 |
| ⑨ | `POST /v1.0/project/users/{userId}/tasks` | 创建 Teambition 任务 |
| ⑩ | `GET https://oapi.dingtalk.com/gettoken` | 获取 access_token（本地缓存，约每 2h 续期 1 次，可忽略） |

> 注：①-⑧ 都通过 `x-acs-dingtalk-access-token` header 认证，token 来自 ⑩ 的缓存。

---

## 二、后端接口 — 钉钉 API 映射

### 2.1 知识库浏览类

| 后端 HTTP 接口 | 钉钉调用链 | 单次调用数 |
|--------------|-----------|----------|
| `GET /ai/knowledge/workspaces` | ① | **1 次** |
| `GET /ai/knowledge/workspaces/<id>/nodes` | ② | **1 次** |
| `GET /ai/knowledge/documents/<id>` (缓存命中) | 无 | **0 次** |
| `GET /ai/knowledge/documents/<id>` (缓存未命中) | ③ → ④（或 ⑤ → ⑥×N sheets） | **2~N+2 次** |

### 2.2 搜索类

| 后端 HTTP 接口 | 钉钉调用链 | 单次调用数 |
|--------------|-----------|----------|
| `POST /ai/knowledge/search` (全局) | ⑦ | **1 次** |
| `POST /ai/knowledge/search` (指定知识库) | ⑧ | **1 次** |
| `POST /ai/knowledge/chunks/search` | 无（本地 FTS/pgvector） | **0 次** |
| `POST /ai/task-analysis/search-kb` | 无（本地 hybrid search） | **0 次** |

### 2.3 创建任务类

| 后端 HTTP 接口 | 钉钉调用链 | 单次调用数 |
|--------------|-----------|----------|
| `POST /ai/create_teambition` | ⑨ | **1 次** |
| MCP `create_teambition_task` | ⑨ | **1 次** |

### 2.4 同步类（🔴 调用量最大）

| 后端 HTTP 接口 | 触发方式 | 钉钉 API 调用量 |
|--------------|---------|---------------|
| `POST /ai/knowledge/sync` | 手动 | `1(①) + N_folders×② + N_files×(③+④+⑤+⑥×M_sheets)` |
| `POST /ai/knowledge/sync-all` | 手动 | 同上 × 知识库数量 |
| `POST /ai/knowledge/sync-and-embedding` | 手动 / daemon 定时 | 同上 |
| daemon 定时任务 | 每天北京时间 04:00 | 同上（全量同步） |

### 2.5 无钉钉调用（纯本地）

| 后端 HTTP 接口 | 访问资源 |
|--------------|---------|
| `/ai/task-analysis/fetch-tasks` | 本地 MySQL |
| `/ai/task-analysis/generate-report` | LLM API（非钉钉） |
| `/ai/knowledge/chat` | LLM API + 本地 retriever |
| `/ai/knowledge/analyze/task` | 本地 MySQL + 本地 retriever |
| `/ai/knowledge/analyze/task/report` | 本地 MySQL + 本地 retriever + LLM |
| `/ai/knowledge/analyze/dashboard` | 本地 MySQL + 本地 retriever + LLM |
| `/ai/tbcreate/*` | 本地 MySQL / 文件系统 |
| `/ai/ttyd/session` | 启动 ttyd 子进程 |
| MCP `get_user_task_context` | 本地 MySQL |
| MCP `search_knowledge_base` | 本地 retriever |
| MCP `analyze_tasks` | 本地 MySQL + 本地 retriever + LLM |

---

## 三、单次全量同步的接口调用拆解

知识库同步的核心逻辑在 `ai/knowledge/routes.py` 的 `_sync_workspace()`:

```
对每个知识库:
  ① GET workspaces              → 1 次
  递归遍历每个节点:
    如果是 FOLDER:
      ② GET nodes?parentNodeId   → 1 次（获取子节点列表）
    如果是 FILE:
      ③ GET nodes/<nodeId>       → 1 次（获取元数据）
      ④ GET .../blocks           → 1 次（尝试获取内容，WORKBOOK 会 400）
      如果 ④ 返回 400（说明是 WORKBOOK 类型）:
        ⑤ GET .../sheets         → 1 次（获取 sheet 列表，DOCUMENT 会 400）
        对每个 sheet:
          ⑥ GET .../ranges/A1:Z500  → 1 次
```

### 3.1 实际数据：一次全量同步（10 个知识库）的接口分布

以 6/1 同步（33,212 次）和 6/2 同步（38,757 次）为样本，取典型值：

| # | 钉钉 API | 典型次数 | 占比 | 说明 |
|---|---------|---------|------|------|
| ③ | `GET .../nodes/<nodeId>` | ~10,800 | 30% | 每个文件的元数据查询 |
| ④ | `GET .../blocks` | ~10,800 | 30% | 每个文件尝试获取文档内容 |
| ⑤ | `GET .../sheets` | ~6,300 | 18% | blocks 返 400 后的 fallback |
| ② | `GET .../nodes` | ~5,000 | 14% | 递归遍历文件夹目录 |
| ⑥ | `GET .../ranges` | ~3,000 | 8% | 每个 WORKBOOK 的每个 sheet 读一次 |
| ① | `GET .../workspaces` | 1 | <0.1% | 获取知识库列表 |
| | **合计** | **~35,000** | 100% | |

```
③ nodes/<id>   ██████████████████████████████  10,800  (30%)
④ blocks       ██████████████████████████████  10,800  (30%)
⑤ sheets       ██████████████████              6,300  (18%)
② nodes(列表)   ██████████████                  5,000  (14%)
⑥ ranges       ████████                        3,000  ( 8%)
① workspaces   ▏                                   1  (<1%)
```

### 3.2 从接口次数反推知识库规模

| 推导项 | 数值 | 依据 |
|--------|------|------|
| 文件总数 | ~10,800 | ③ = ④，每个文件都查询 |
| 其中普通文档（ALIDOC） | ~4,500 | blocks 调用成功的文件 |
| 其中表格（WORKBOOK） | ~6,300 | blocks 失败 → 调 sheets 的文件 |
| 文件夹总数 | ~5,000 | ② 每次列出一个文件夹的子节点 |
| 表格 sheet 总数 | ~3,000 | ⑥ 每个 sheet 读一次 |

### 3.3 每类文件的 API 调用开销

| 文件类型 | 调用链 | 次数 |
|---------|--------|------|
| 普通文档（ALIDOC） | ③ + ④ | **2 次** |
| 表格（WORKBOOK，平均 2 个 sheet） | ③ + ④(400) + ⑤ + ⑥×2 | **5 次** |

### 3.4 单次全量同步的浪费分析

| 浪费类型 | 次数 | 占比 | 说明 |
|---------|------|------|------|
| ④ blocks 调了 WORKBOOK（必然 400） | ~6,300 | 18% | 应跳过，直接用 ⑤ |
| ⑤ sheets 调了 DOCUMENT（必然 400） | ~4,500 | 13% | ④ 已经成功，不会走到这里 |
| **合计可避免的浪费** | **~10,800** | **31%** | 近 1/3 调用是浪费 |

> 浪费根源：`get_node_detail` ③ 的返回结果中已经包含 `category` 字段（`ALIDOC` / `WORKBOOK` / `OTHER`），但代码没有利用它来做路由，而是对每个文件都"先试 blocks 再 fallback sheets"。

---

## 四、实际日志分析

### 4.1 总体数据

| 指标 | 数值 |
|------|------|
| 日志时间范围 | 2026-05-26 08:49 ~ 2026-06-03 00:17（7.6 天） |
| 总记录数 | **79,260** |
| 日均调用量 | **~10,400 次/天** |
| 日志大小 | 11.5 MB |

### 4.2 按 API 端点分布

| 钉钉 API | 调用次数 | 占比 |
|---------|---------|------|
| `GET .../nodes/<id>`（节点详情） | 23,059 | 29.1% |
| `GET .../blocks`（文档内容） | 22,666 | 28.6% |
| `GET .../sheets`（表格 sheet 列表） | 13,671 | 17.2% |
| `GET .../nodes`（节点列表） | 12,766 | 16.1% |
| `GET .../ranges`（表格数据） | ~7,000+ | ~9% |
| `GET .../workspaces`（知识库列表） | 9 | <0.1% |

### 4.3 按 HTTP 状态码分布

| 状态码 | 次数 | 占比 | 说明 |
|--------|------|------|------|
| 200 | 53,729 | 67.8% | 正常成功 |
| 400 | 21,280 | 26.9% | WORKBOOK/DOCUMENT 类型不匹配 |
| 500 | 3,271 | 4.1% | 钉钉服务端内部错误 |
| 403 | 891 | 1.1% | 权限不足 |
| 503 | 79 | 0.1% | 服务不可用 / 限流 |
| 404 | 1 | <0.1% | 未找到 |

> ⚠️ **成功率仅 67.8%**。约 27% 的 400 错误是预期行为（WORKBOOK 用 blocks API 失败后 fallback 到 sheets），但仍有约 **5.3% 是真实失败**（4,241 次 500/403/503）。

### 4.4 400 错误细节

| 端点 | 400 次数 | 原因 |
|------|---------|------|
| `GET .../sheets` | 10,911 | DOCUMENT 类型被当成 workbook，返回 400 |
| `GET .../blocks` | 10,361 | WORKBOOK 类型被当成 document，返回 400 |

> 这 21,272 次「类型不匹配」的 400 调用是当前代码流程的**必然产物**：对每个文件都先 try blocks，失败后才 try sheets。相当于每个文件浪费 1 次 API 调用。

### 4.5 每日调用趋势

| 日期 | 调用量 | 说明 |
|------|--------|------|
| 2026-05-26 | 562 | 初始少量测试 |
| 2026-05-27 | 1,661 | 测试 + 浏览 |
| 2026-05-28 ~ 05-31 | 0 | 服务未运行 / 未产生日志 |
| 2026-06-01 | **33,212** | 🔴 全量同步（约 10 个知识库） |
| 2026-06-02 | **38,757** | 🔴 全量同步（daemon 凌晨触发） |
| 2026-06-03 | 5,068 | 部分同步 / 浏览 |

---

## 五、不同业务场景的钉钉调用量估算

| 消耗等级 | 业务场景 | 单次钉钉调用量 | 发生频率 |
|---------|---------|--------------|---------|
| 🔴🔴🔴 极高 | 全量同步 10 个知识库 | **~35,000 次** | daemon 每天凌晨 |
| 🔴🔴 高 | 单知识库同步（按比例） | **~3,500 次** | 手动触发 |
| 🟡 中 | 用户浏览知识库一次 | **~8-10 次** | 按需使用 |
| 🟢 低 | 创建 TB 任务 | **1 次** | 按需使用 |
| 🟢 零 | 任务分析 / AI 聊天 / MCP 工具 | **0 次** | 日常高频 |

---

## 六、优化建议

### 1. 降低 daemon 同步频率（最大收益）
当前每天凌晨 04:00 全量同步一次，每次产生约 **35,000 次**调用。建议改为**每周 1-2 次**（如周一/周四凌晨），或改为增量同步模式。

### 2. 消除类型不匹配的 wasted API call（~31% 节省）
`get_node_detail` 返回的元数据中包含 `category` 字段（`ALIDOC` / `WORKBOOK` / `OTHER`）。
同步时可根据 `category` 直接调用正确的 API，避免每次都先 try blocks 再 fallback。

当前代码在 `_sync_workspace` 中：
```python
blocks = client.get_document_blocks(nid)   # WORKBOOK 会 400 → 浪费 ~6,300 次
if not blocks.get("ok"):
    sheets = client.get_workbook_sheets(nid)  # 实际这里是 WORKBOOK，不会浪费
```

建议改进：在 `get_node_detail` 后根据 `category` 字段区分类型，只调正确的 API。每次全量同步可节省约 **10,800 次**调用（31%）。
```python
# 优化后示例
meta = client.get_node_detail(nid)
category = meta.get("data", {}).get("category", "")
if category == "WORKBOOK":
    sheets = client.get_workbook_sheets(nid)  # 直接调，跳过 blocks
else:
    blocks = client.get_document_blocks(nid)   # 直接调，跳过 sheets  fallback
```

### 3. 增量同步代替全量同步
`list_nodes` 返回的节点信息包含 `modifiedTime`。可以只对修改过的文档重新获取内容，对未修改的文档跳过。可减少 90%+ 的同步调用量。

### 4. 关注真实失败（5.3%）
- **500 错误**（3,271 次）：钉钉服务端问题，建议加重试机制
- **403 错误**（891 次）：权限不足，检查 union_id 对应的用户是否有对应知识库的访问权限
- **503 错误**（79 次）：可能是触发了钉钉限流

### 5. 确认钉钉 API 配额
钉钉 API 通常有调用频率限制（QPS / 日配额），需确认：
- 日调用上限是多少？
- ~8,000 次/天的同步是否会触发限流？
- 503 错误是否已经是限流的结果？

---

## 七、总结

| | 数值 |
|---|------|
| 7.6 天总调用量 | **79,260 次** |
| 日均 | **~10,400 次/天** |
| 单次全量同步 | **~35,000 次** |
| 高峰期 | **~38,757 次/天**（全量同步日） |
| 实际成功率 | **67.8%** |
| 可优化浪费（类型不匹配） | **~31%**（~10,800 次/同步） |
| 真实失败（500/403/503） | **~5.3%** |

**关键结论：**
- 同步操作占 **95%+** 的钉钉 API 调用量，浏览/搜索/创建任务等前端交互几乎不消耗
- 每天凌晨 daemon 全量同步是最大开销来源（**~35,000 次/天**）
- 任务分析、AI 聊天、MCP 等高频功能**完全不走钉钉 API**，不影响配额
- 约 **31%** 的调用是"类型不匹配"的浪费——`category` 字段已在第③步返回但未利用，导致每个文件都多调 1 次
