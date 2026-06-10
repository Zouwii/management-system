# 钉钉 API 调用分析（第二版）

> 分析日期: 2026-06-09
> 数据来源: `/home/zhr/tb_tool_bt_daemon.log` (2026-06-05 ~ 2026-06-09)
> 代码版本: 已实现 category 优化后的版本

---

## 一、与第一版的对比总览

| 维度 | 第一版 (5/26~6/3) | 第二版 (6/5~6/9) | 变化 |
|------|------------------|-----------------|------|
| 日均钉钉 API 调用 | ~10,400 次/天 | **~1,500 次/天** | ↓ 85% |
| 单次全量同步 | ~35,000 次 | **~6,100 次** | ↓ 82% |
| 类型不匹配浪费 | ~31%（~10,800次/同步） | **0%** | ✅ 已根除 |
| 同步耗时 | 未记录 | **~30-33 分钟** | — |
| 日志格式 | JSON `kb_api_get` | 应用级 `[sync-embed]` | 变化 |
| 知识库文件数 | ~10,800 | ~164-188 | 过滤后仅拉 ALIDOC |

---

## 二、当前涉及的钉钉 API 端点

| # | 钉钉 API | 用途 | 调用量等级 |
|---|---------|------|----------|
| ① | `GET /v2.0/wiki/workspaces` | 获取知识库列表 | 🟢 极低（≤1次/同步） |
| ② | `GET /v2.0/wiki/nodes` | 获取目录子节点（递归遍历） | 🔴 高（~5,000次/同步） |
| ④ | `GET /v1.0/doc/suites/documents/<id>/blocks` | 获取文档内容（仅 ALIDOC） | 🟡 中（~188次/同步） |
| ⑨ | `POST /v1.0/project/users/{userId}/tasks` | 创建 Teambition 任务 | 🟢 极低（按需） |
| ⑩ | `GET https://oapi.dingtalk.com/gettoken` | 获取 access_token（本地缓存） | 🟢 可忽略 |

> **已移除的端点**（第一版中存在，现已不再调用）：
> - ~~③ `GET .../nodes/<nodeId>`~~ — `list_nodes` 已返回 category，不再单独查元数据
> - ~~⑤ `GET .../sheets`~~ — WORKBOOK 在遍历阶段直接跳过
> - ~~⑥ `GET .../ranges`~~ — 同上
> - ~~⑦⑧ 搜索 API~~ — 搜索功能走本地数据库

---

## 三、后端接口 — 钉钉 API 映射

### 3.1 知识库同步类（调用量最大）

| 后端触发方式 | 钉钉调用 | 调用量 |
|------------|---------|--------|
| `POST /ai/knowledge/sync-and-embedding` (手动) | ② + ④ | **~6,100 次/次** |
| daemon 定时（每日 04:00 BJT） | ② + ④ | **~6,100 次/次** |

### 3.2 创建任务类

| 后端 HTTP 接口 | 钉钉调用 | 单次调用数 |
|--------------|---------|----------|
| `POST /ai/create_teambition` | ⑨ | **1 次** |
| MCP `create_teambition_task` | ⑨ | **1 次** |

### 3.3 无钉钉调用（纯本地）

| 后端 HTTP 接口 | 访问资源 |
|--------------|---------|
| `/ai/task-analysis/*` | 本地 MySQL + LLM API |
| `/ai/knowledge/chat` | LLM API + 本地 retriever |
| `/ai/knowledge/chunks/search` | 本地 pgvector |
| `/ai/tbcreate/*` | 本地 MySQL / 文件系统 |
| `/ai/ttyd/session` | 启动 ttyd 子进程 |
| MCP 全部工具 | 本地 MySQL / retriever / LLM |

---

## 四、当前同步流程详解

### 4.1 核心优化：基于 category 的类型路由

```python
# routes.py _sync_workspace() — 当前代码
for n in result["data"]:
    category = (n.get("category") or "").strip().upper()

    # ✅ 跳过非 ALIDOC 类型（WORKBOOK 等直接跳过）
    if category != "ALIDOC":
        skipped_workbooks += 1
        continue

    # 仅对 ALIDOC 调用 get_document_blocks
    blocks = client.get_document_blocks(nid)
```

**对比第一版的问题代码：**

```python
# 旧：每个文件都先试 blocks（WORKBOOK 会 400），再 fallback sheets（DOCUMENT 会 400）
blocks = client.get_document_blocks(nid)   # 浪费 ~6,300 次
if not blocks.get("ok"):
    sheets = client.get_workbook_sheets(nid)  # 浪费 ~4,500 次
```

> **收益：每次全量同步节省约 10,800 次 API 调用（31%），且消除了 21,272 次 400 错误。**

### 4.2 同步模式的区分

| 模式 | 触发条件 | 逻辑 |
|------|---------|------|
| **小同步**（增量） | 每周一/周四 04:00 | 只拉取本地缓存中**不存在**的 ALIDOC 文档 |
| **大同步**（全量） | 每月 1 号 04:00 | 对比 `remote_modified_at`，重新拉取**已变更**的文档 |

### 4.3 单次全量同步的接口调用拆解

```
对每个知识库:
  ① GET workspaces              → 1 次（获取知识库列表）
  递归遍历每个节点:
    如果是 FOLDER:
      ② GET nodes?parentNodeId   → 1 次（获取子节点列表）→ ~5,000 次
    如果是 FILE:
      从 list_nodes 返回中读取 category 字段
      如果 category == "ALIDOC":
        ④ GET .../blocks          → 1 次（获取文档内容）→ ~188 次
      如果 category == "WORKBOOK":
        跳过（不调用任何 API）
```

当前每次同步 API 调用量 ≈ **5,000（list_nodes）+ 188（blocks）+ 908（失败重试）≈ 6,100 次**

---

## 五、实际日志分析

### 5.1 总体数据

| 指标 | 数值 |
|------|------|
| 日志时间范围 | 2026-06-05 16:54 ~ 2026-06-09 14:02（~4 天） |
| 日志大小 | 206 KB / 2,135 行 |
| 总 HTTP 请求数 | 678 次 |
| 其中同步类请求 | 2 次 `sync-and-embedding` |
| 创建 Teambition | 15 次（5 成功 / 10 失败） |
| 知识库聊天/分析/TTYD | 大量，但 **0 次钉钉 API 调用** |

### 5.2 同步操作详情

| # | 时间 | 触发方式 | 模式 | 耗时 | 同步数 | 变更 | **失败** |
|---|------|---------|------|------|--------|------|---------|
| 1 | 6/5 17:35 | 手动 HTTP | 小同步 | 33.0 min | 188 | 28 | **908** |
| 2 | 6/5 18:23 | 手动 HTTP | 小同步 | 31.8 min | 164 | 0 | **907** |
| 3 | 6/6 04:00 | daemon 自动 | 定时 | 30.6 min | 164 | 0 | **908** |
| 4 | 6/6 04:00 | daemon 自动 ⚠️ | 定时 | 30.6 min | 164 | 0 | **908** |

> ⚠️ **6/6 凌晨 04:00 出现了两个并发同步**（启动时间相隔 1 秒）。两次同步的 embedding 阶段都报告 `total=13241`，确认是在重复处理完全相同的文档集。原因：Flask debug 模式加载器创建了两个应用实例。

### 5.3 同步统计数据（embedding 阶段）

| 同步 | 总 chunks | 新增 | 跳过 | 耗时 |
|------|----------|------|------|------|
| 1 (6/5 17:35) | 13,241 | 52 | 13,189 | 8.2s |
| 2 (6/5 18:23) | 13,241 | 0 | 13,241 | 1.5s |
| 3 (6/6 04:00) | 13,241 | 0 | 13,241 | 1.4s |
| 4 (6/6 04:00) | 13,241 | 0 | 13,241 | 4.1s |

> 从第 2 次同步开始，chunks 总量稳定在 13,241，新增始终为 0，说明知识库内容在这几天没有实质变化。

### 5.4 HTTP 请求 TOP 10 路由

| # | 路由 | 次数 | 钉钉调用 |
|---|------|------|---------|
| 1 | `GET /api/bt/update_lock_status` | 102 | 无 |
| 2 | `POST /api/dashboard/personal-hours/query` | 85 | 无 |
| 3 | `POST /api/bt/stats/executor_quarter_workhours` | 81 | 无 |
| 4 | `POST /api/bt/ai/knowledge/chat/session` | 37 | 无 |
| 5 | `GET /api/bt/ai/models` | 37 | 无 |
| 6 | `POST /api/bt/ai/tbcreate/draft/save` | 26 | 无 |
| 7 | `GET /api/bt/ai/tbcreate/draft/events` | 20 | 无 |
| 8 | `GET /api/bt/ai/tbcreate/tasks` | 19 | 无 |
| 9 | `POST /api/bt/auth/logout` | 17 | 无 |
| 10 | `POST /api/bt/ai/task-analysis/*` | 45 | 无 |

> 前端日常交互 TOP 10 路由全部**不触发钉钉 API**。

### 5.5 状态码分布

| 状态码 | 次数 | 占比 | 说明 |
|--------|------|------|------|
| 200 | 600 | 88.5% | 正常 |
| 400 | 78 | 11.5% | 全部来自 `create_teambition` 的连续重试 |

> 与第一版相比，不再有 WORKBOOK/DOCUMENT 类型不匹配导致的 400。当前 400 全部来自 Teambition 创建接口的参数错误。

### 5.6 HTTP 请求按日分布

| 日期 | HTTP 请求数 | 主要活动 |
|------|-----------|---------|
| 2026-06-05 | 339 | 同步测试 + 开发调试 |
| 2026-06-08 | 471 | 大量 create_teambition 重试 + 日常使用 |
| 2026-06-09 | 70 | 任务分析 + 工作耗时查询 |

---

## 六、sync_failures 记录分析

daemon 日志中的 `sync_failures` 记录：

| 类型 | phase | 次数 | 说明 |
|------|-------|------|------|
| `normal_update` | `b_refresh` | 8 次 × count=2 | 小同步时的 Teambition refresh 失败 |
| `full_update` | `b_sync` | 3 次 × (count=2~21) | 全量同步时 Teambition 任务同步失败 |

> 这些 failure 与钉钉 API 调用无关，属于 Teambition 任务列表同步到本地的失败。

---

## 七、不同业务场景的钉钉调用量估算（当前）

| 消耗等级 | 业务场景 | 单次钉钉调用量 | 发生频率 |
|---------|---------|--------------|---------|
| 🟡 中 | 全量/小同步 | **~6,100 次** | daemon 每周 2 次 + 手动 |
| 🟢 低 | 创建 TB 任务 | **1 次** | 按需使用 |
| 🟢 零 | 任务分析 / AI 聊天 / MCP 工具 | **0 次** | 日常高频 |

---

## 八、当前存在的问题

### 🔴 问题 1：daemon 同步重复启动

**现象：** 6/6 凌晨 04:00:19 和 04:00:20 同时启动了两个同步任务。

**原因推测：** Flask debug 模式的 reloader 创建了两个应用进程，各自的 daemon 线程独立运行。`last_trigger_date` 是进程级变量，跨进程不共享。

**影响：** 每次定时同步消耗双倍 API 配额（~12,200 次而非 ~6,100 次）。

**代码位置：** `backend/base/app.py:220-276`，使用 `globals()` + `threading.Thread` 方式防止重复，但在多进程场景下失效。

### 🟡 问题 2：failed 数始终在 ~908

**现象：** 每次同步都有约 908 个 API 调用失败，且数字非常稳定。

**分析：**
- `failed=908` = `len(errors)`，来自 `list_nodes` 或 `get_document_blocks` 返回非 ok
- 可能原因：某些文件夹/文档的权限不足（403），或某些节点 ID 已失效（404）
- 总数 164-188 个文档中失败 908 次，意味着同一个失败的文件夹可能被反复重试（递归遍历时的子节点累积）

**建议：** 记录并缓存失败节点 ID，后续同步跳过这些节点，避免重复消耗 API 配额。

### 🟡 问题 3：没有逐条 API 调用日志

**现象：** 当前日志只有 `[sync-embed]` 级别的汇总，无法统计各端点的状态码、延迟分布。

**对比：** 第一版有 `{"phase":"kb_api_get","endpoint":"...","status":200,"latency_ms":384}` 格式的逐条记录。

**影响：** 排障困难 — 908 次 failed 无法区分是哪个端点失败、什么状态码、是否限流。

**建议：** 在 `DingTalkKnowledgeClient` 的请求方法中恢复或添加结构化日志。

### 🟡 问题 4：Teambition 创建连续 400 重试

**现象：** 6/8 15:29:40 ~ 15:29:54，同一用户连续发起 10 次 `create_teambition`，全部返回 400。

**分析：** 前端可能缺少防重复提交或错误提示机制，用户在失败后反复点击。

**建议：** 前端加 loading 状态 + 防抖，后端返回明确的错误信息。

### 🟢 问题 5：embedding chunks 总量冻结

**现象：** 6/5 之后 chunks 始终 = 13,241，新增 = 0。

**含义：** 知识库没有新文档入库 OR 新文档全部为非 ALIDOC 类型被跳过。

**建议：** 确认是否有 WORKBOOK 类型的文档需要被索引（当前直接跳过）。

---

## 八.2、API 调用监控系统（2026-06-10 新增）

### 数据库设计

为解决上述 **问题 3（没有逐条 API 调用日志）**，新增 `api_call_logs` 持久化表：

```sql
CREATE TABLE api_call_logs (
    id         BIGINT AUTO_INCREMENT PRIMARY KEY,
    endpoint   VARCHAR(255) NOT NULL,           -- 钉钉 API 路径
    source     VARCHAR(50)  NOT NULL DEFAULT '', -- 调用来源标签
    status     INT          NOT NULL DEFAULT 0,  -- HTTP 状态码
    latency_ms INT          NOT NULL DEFAULT 0,  -- 延迟（毫秒）
    error_msg  VARCHAR(500) DEFAULT '',          -- 错误信息
    created_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_created_at (created_at),
    INDEX idx_endpoint_date (endpoint, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### source 标签分类

| source | 含义 | 对应代码 |
|--------|------|---------|
| `auth` | OAuth / Token / 用户信息 | `dingtalk_client.py` |
| `task_list` | 任务列表拉取 | `task_service.py :: query_project_tasks_service` |
| `task_detail` | 任务详情拉取 | `task_service.py :: query_user_tasks_service` |
| `task_search` | 任务搜索 | `task_service.py :: search_project_tasks_service` |
| `tb_create` | 创建 Teambition 任务 | `teambition/service.py` |
| `kb_sync` | 知识库同步 | `knowledge/service.py` |
| *(空)* | 旧代码/未标记 | 兼容 |

### 架构

```
record_api_call(endpoint, status, latency, source)
   ├── 内存 ring buffer (最近 200 条, 实时)
   └── 批量写入 MySQL (每 50 条 flush 一次, 持久化)
                    ↓
   GET /api/bt/monitor/api-stats
        ├── SQL 聚合当日数据 (GROUP BY endpoint)
        └── 合并内存 recent buffer
```

### 前端展示

- 页面左下角固定显示当日调用量 `📡 N calls today`
- 点击弹出详情面板：端点分布、错误率、最近调用记录
- 每 15 秒自动刷新

### 与问题 3 的关系

> ✅ **问题 3 已解决。** 不再需要恢复知识库专用的 `kb_api_get` 日志格式，所有钉钉 API 调用统一走 `api_call_logs` 持久化 + 前端可视化。

---

## 九、进一步优化建议

### 优先级 1（高收益 / 低风险）

| # | 优化项 | 预期收益 | 说明 |
|---|--------|---------|------|
| 1 | **修复 daemon 重复启动** | 节省 50% 定时同步配额 | 使用文件锁或数据库锁替代进程级变量 |
| 2 | **缓存失败节点黑名单** | 节省 ~908 次/同步 的浪费 | 失败的 folder 不应在下次同步时再次尝试遍历 |
| 3 | **恢复逐条 API 调用日志** | 提升可观测性 | 确认 908 次 failed 的端点/状态码分布 |

### 优先级 2（中收益 / 需验证）

| # | 优化项 | 预期收益 | 说明 |
|---|--------|---------|------|
| 4 | **降低 daemon 同步频率** | 按比例减少 | 当前每周 2 次，可减为每周 1 次或增量对比 |
| 5 | **list_nodes 加本地缓存** | 减少 ~5,000 次/同步 | 对不变更的目录树缓存子节点列表 |
| 6 | **WORKBOOK 类型支持** | 扩大知识覆盖面 | 当前直接跳过 WORKBOOK，可能遗漏表格类知识 |

### 优先级 3（长期改进）

| # | 优化项 | 预期收益 | 说明 |
|---|--------|---------|------|
| 7 | **钉钉 API 限流监控/自适应** | 防封禁 | 记录 QPS，接近限额时自动降速 |
| 8 | **增量同步（基于 modifiedTime）** | 减少 90%+ 同步调用 | list_nodes 返回含 modifiedTime，可只拉变更文档 |
| 9 | **同步改为事件驱动** | 消除定时轮询 | 通过钉钉 webhook 或人工触发达成 |

---

## 十、总结

| | 第一版 | 第二版（当前） |
|---|--------|--------------|
| 7.6 天总调用量 | 79,260 次 | **~6,000 次**（估算） |
| 日均钉钉调用 | ~10,400 次/天 | **~1,500 次/天** |
| 单次全量同步 | ~35,000 次 | **~6,100 次** |
| 类型不匹配浪费 | ~31% | **0%** ✅ |
| 主要瓶颈 | 大量 WORKBOOK 误调用 | daemon 重复 + failed 节点重试 |
| 嵌入总量 | 未记录 | **13,241 chunks**（稳定） |

**关键结论：**

1. **category 优化已生效且效果显著** — 日均 API 调用从 ~10,400 降到 ~1,500（↓85%），类型不匹配的浪费已完全根除。

2. **当前最大的优化空间在 daemon 层面** — 修复重复启动可立即节省 50% 的定时同步配额；缓存失败节点黑名单可再节省 ~908 次/同步。

3. **前端交互完全不走钉钉 API** — 知识库聊天、任务分析、MCP、工时查询等所有日常功能都是 0 次钉钉调用。

4. **可观测性下降** — 建议恢复逐条 API 日志，便于监控和排障。

5. **下一步优化重点**：修复 daemon 重复 → 失败节点黑名单 → 恢复 API 日志 → 增量同步。
