# 创单路径设计

> 日期: 2026-06-10
> 三条独立的 Teambition 任务创建路径，职责分离。

---

## 路径 ① — 公共 HTTP 创单接口（前端正式流程）

```
前端"确认创建"按钮
  → POST /api/bt/ai/create_teambition
    → ai/teambition/routes.py :: ai_create_teambition()
      → ai/teambition/service.py :: create_task(draft)
        → build_payload(draft) → DingTalk API POST /v1.0/project/users/{userId}/tasks
    ← { taskId, taskUrl }
    ← 清除 draft.json / draft_changed.flag
```

**调用方**：前端用户点击确认按钮

**特点**：
- session 认证，自动注入 userId
- 创建成功后清除草稿文件
- 必须经过前端界面提交

---

## 路径 ② — TTYD 交互式 Draft 流程

```
TTYD 中 Claude（按 CLAUDE.md / SKILL.md 指引）:
  1. 阅读 AI_TASK_CONTEXT.md 了解用户任务全景
  2. 一问一答收集信息：
     ① 标题(≤18字) → ② 工时类型 → ③ 背景 → ④ 需求描述+产出 → ⑤ 起止时间
  3. 用户确认后，写入 draft.json
  4. curl POST /api/bt/ai/tbcreate/draft/notify → SSE 广播
                                                    ↓
前端 SSE 监听 ← 收到 draft_updated 事件 → 自动刷新草稿面板
  5. Claude 询问用户：
     "1、右侧面板有修改，还需继续交流  2、已创建成功，开始新一轮任务创建"
  6. 用户选 1 → 同步 draft_changed.flag → 继续在当前草稿上协作
     用户选 2 → 系统清空 draft.json → 从步骤①开始新一轮
```

**调用方**：TTYD 中的 Claude CLI

**特点**：
- Claude 只写 draft.json，不调钉钉 API
- 最终创单权在前端用户手里（用户点击"确认创建"→ 路径①）
- 完整的交互循环：创完一个可以继续创下一个
- 支持右侧面板同步（draft_changed.flag）
- SSE 事件：Claude 写文件 → curl notify → 前端刷新

**指导文件**：`ai/skills/2_tb_create/SKILL.md`（复制到工作区为 `CLAUDE.md`）

---

## 路径 ③ — MCP 直接创单（纯 CLI，无 SSE）

```
DingTalk Bot / MCP 客户端:
  → 调用 tb_create prompt → 获取指令
  → get_user_task_context → 了解任务全景
  → 对话收集信息 → 生成草稿 → 用户确认
  → 调用 create_teambition_task MCP Tool
    → ai/mcp/tools/task_create.py
      → ai/teambition/service.py :: create_task(draft)
    ← { success, taskId, taskUrl }
```

**调用方**：DingTalk Bot 等 MCP 客户端（SSE 或 stdio）

**特点**：
- 纯 CLI 交互，不走前端，不走 SSE 通知
- 不写 draft.json
- 底层调用与路径①共享 `create_task()`
- 参数校验由 MCP tool 负责

**指导文件**：`ai/mcp/server.py` → `tb_create` prompt

---

## 架构关系图

```
                         ┌─────────────────────────────────┐
                         │   ai/teambition/service.py       │
                         │         create_task()            │
                         │   → DingTalk API 创单            │
                         └──────┬──────────────┬────────────┘
                                ↑              ↑
                       路径① HTTP API    路径③ MCP Tool
                       (前端确认后调)    (Bot CLI 直接调)
                                ↑
                         前端用户点击"确认创建"
                                ↑
                       路径② draft.json
                       (Claude 交互 → 写草稿 → SSE 通知)
```

---

## 决策矩阵

| 场景 | 使用路径 | 指导文件 |
|------|---------|---------|
| 用户在前端 Chat UI 确认创单 | ① | `ai/teambition/routes.py` |
| 用户在 TTYD 中与 Claude 交互创单 | ② | `ai/skills/2_tb_create/SKILL.md` |
| DingTalk Bot / 外部 MCP 创单 | ③ | `ai/mcp/server.py` prompt |
| 外部系统通过 MCP 集成 | ③ | MCP tool 直接调用 |

---

## 关键约束

1. **路径② 和 路径③ 互不干扰** — TTYD Claude 读 SKILL.md（路径②），MCP Bot 读 prompt（路径③）
2. **路径② 不调钉钉 API** — Claude 只写 draft.json，创单由前端通过路径①完成
3. **路径③ 不走前端** — 不写 draft.json，不调 SSE，纯 CLI 完成
4. **三条路径底层共享 `create_task()`** — payload 构建逻辑一致
