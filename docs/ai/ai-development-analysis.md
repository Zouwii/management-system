# AI 应用开发方法调研 & management-system AI 现状分析

> 调研日期：2026-05-14
> 范围：management-system 现有 AI 功能 + 业界 AI 应用开发主流方法

---

## 一、management-system AI 现状总览

### 1.1 已实现的 AI 功能

当前系统包含三条 AI 能力线：

| 能力线 | 技术实现 | 成熟度 | 说明 |
| --- | --- | --- | --- |
| **AI 任务助手（对话式草稿生成）** | Python 规则引擎 + 前端聊天 UI | 可用 | 基于正则匹配和关键词推断，非真正的 LLM 对话 |
| **AI 交互终端（ttyd 嵌入）** | ttyd + Claude CLI + one-api 网关 | 可用 | 在页面 iframe 中嵌入完整 Claude CLI 终端 |
| **AI Teambition 任务创建** | 钉钉 OpenAPI 调用 | 可用 | 将结构化草稿转为钉钉任务单，含默认模板 |

### 1.2 架构分层

```
前端 (React)
├── AIAnalysisPage.jsx          # 用户 UI：聊天、草稿编辑、ttyd 终端、分析面板
├── api/dashboard.js            # API 层：mock/real 双模式切换
└── mock/platformData.js        # 4 条静态 AI insight 样例

后端 (Flask)
├── route_registry/ai_mission.py  # REST API：对话管理、消息发送、草稿确认
├── ai/terminal/routes.py         # REST API：ttyd 会话创建与复用
├── ai/terminal/session.py        # ttyd 进程、端口、TTL 回收、环境变量管理
├── ai/terminal/launcher.sh       # ttyd 内部启动 claude CLI 的唯一脚本
├── services/ai_task_assistant_service.py   # 对话状态管理、草稿合并（规则引擎）
├── services/ai_task_context_service.py     # DB 任务上下文读取、Markdown 生成
├── services/ai_mission_service.py          # 钉钉任务创建 payload 构建与调用
├── ai/config.json               # one-api 网关配置
└── ai/project_memory/           # AI 行为规则（task_ticket / task_analysis / data_contracts）
```

### 1.3 关键设计决策

1. **ttyd 终端方案**：旧 PTY 聊天链路已移除，当前只保留终端嵌入模式——用户通过 iframe 直接操作 Claude CLI
2. **多用户隔离**：按 `ownerKey` → SHA256 哈希 → 24 字符安全目录名，进程、端口、工作区独立
3. **one-api 网关**：固定 `http://one-api.server22.jz`，支持 claude / kimi / minimax / step / mimo / glm / deepseek 七种模型
4. **任务助手"假 AI"**：当前对话式任务草稿生成并非调用 LLM，而是服务端 Python 正则匹配 + 规则推断（`_infer_task_type`、`_infer_work_type`、`_infer_participation` 等函数）
5. **上下文注入**：在用户工作区写入 `AI_TASK_CONTEXT.md` 和 `CLAUDE.md`，供 ttyd 中的 Claude CLI 启动时读取

---

## 二、业界 AI 应用开发主流方法

### 2.1 三种架构范式

#### 范式 A：嵌入式终端（当前方案）

```
用户 → 前端 iframe → ttyd WebSocket → bash → claude CLI
```

- **代表工具**：Claude Code CLI、Gemini CLI、GitHub Copilot CLI、ttyd
- **适用场景**：开发者工具、内部管理平台、需要完整 shell 环境的高级用户
- **优点**：直接复用 CLI 全部能力，无需开发对话 UI、工具链、权限系统
- **缺点**：无法定制交互流程、前端不可控、多用户资源开销大、无法做流式响应定制

#### 范式 B：Chat API / 托管对话

```
用户 → 前端聊天 UI → 后端 API → LLM Provider (Anthropic/OpenAI)
```

- **代表框架**：Vercel AI SDK、LangChain Expression Language (LCEL)、LlamaIndex
- **适用场景**：面向终端用户的 AI 产品、需要定制 UI 和交互流程的场景
- **优点**：前端可控、支持流式响应、可做 prompt 工程和 RAG、用户体验好
- **缺点**：需要自建对话管理、历史存储、token 计算等基础设施

#### 范式 C：Agent 框架（工具调用 / 多步推理）

```
用户 → Agent 编排层 → 工具集 (API/DB/文件) → 多步推理与执行 → 结果
```

- **代表框架**：
  - **LangChain / LangGraph**：基于图的 Agent 状态机，Python/JS 双生态
  - **CrewAI**：多 Agent 角色扮演与协作
  - **AutoGen**（微软）：多 Agent 对话与代码执行
  - **Anthropic SDK 原生**：直接使用 tool_use / tool_result 实现 ReAct 循环
  - **MCP (Model Context Protocol)**：标准化的工具/资源/提示接入协议
- **适用场景**：复杂的自动化流程、需要调用外部 API 的任务、多角色协作
- **优点**：能执行多步复杂任务、可调用数据库和 API、可审计中间步骤
- **缺点**：开发复杂度高、token 消耗大、调试困难、响应延迟高

### 2.2 核心能力矩阵

| 能力 | 嵌入式终端 | Chat API | Agent 框架 |
| --- | --- | --- | --- |
| 对话式交互 | ✅ (CLI) | ✅ | ✅ |
| 流式响应 | ✅ (终端输出) | ✅ | ✅ (逐 tool) |
| 自定义 UI | ❌ (iframe 黑盒) | ✅ | ✅ |
| 工具调用 (Function Calling) | ✅ (CLI 内置) | ✅ (API tool_use) | ✅ (核心能力) |
| 数据库查询 | ❌ (需手动) | ✅ (RAG/tool) | ✅ (原生) |
| 多 Agent 协作 | ❌ | ❌ | ✅ |
| 可观测性 | 低 | 中 | 高 (LangSmith 等) |
| 前端集成复杂度 | 低 | 中 | 高 |
| 资源消耗 | 高 (每用户一进程) | 低 (无状态 API) | 中-高 |
| 模型无关性 | ✅ (one-api 切换) | ✅ | ✅ |

### 2.3 MCP (Model Context Protocol) 生态

MCP 是 Anthropic 推出的 Agent 工具标准化协议，已成为 2025-2026 最重要的 AI 应用基础设施之一：

- **架构**：MCP Server（提供工具/资源) ↔ MCP Client（Claude 等 AI 应用）
- **典型工具**：数据库查询、文件系统操作、API 调用、Slack/GitHub/Jira 集成
- **优势**：一次开发 MCP Server，多个 AI 应用共享；标准化协议降低集成成本
- **与当前系统的关系**：Claude CLI 原生支持 MCP，如果本系统需要 Agent 化，MCP 是最自然的工具层选择

### 2.4 RAG (检索增强生成) 模式

当前系统已有 RAG 雏形：

```
DB 任务数据 → Python 服务层 → Markdown 文档 → Claude CLI 读取（手动）
```

完整 RAG 演进路径：

```
DB 任务数据 → Embedding → 向量数据库 → 语义检索 → Prompt 注入 → LLM 生成
```

### 2.5 2025-2026 关键趋势

1. **Agent 到 Agentic Workflow 的升级**：从单次 tool_call 到多步有状态工作流
2. **MCP 成为标准**：越来越多的平台内置 MCP Server/Client 支持
3. **Prompt 即代码**：System prompt、few-shot examples、rules 进入版本控制
4. **可观测性优先**：LangSmith、Braintrust、Weave 等观测平台成为标配
5. **小模型 + 大模型协同**：路由层（如 one-api）将简单任务分发给小模型、复杂任务分发给大模型
6. **Human-in-the-Loop**：关键操作（如创建任务单）必须有确认节点

---

## 三、当前系统 AI 实现分析

### 3.1 架构优势

1. **快速落地**：ttyd 方案绕过对话 UI 开发，直接复用 Claude CLI 全部能力，2 周内可用
2. **多模型灵活切换**：one-api 网关 + 脚本菜单支持 7 种模型，无需改前端代码
3. **用户隔离完整**：SHA256 哈希 + 独立端口 + 独立工作区，安全基本到位
4. **规则文档化**：`project_memory/` 中的规则文件可作为 AI prompt 直接注入，人工也可维护
5. **上下文注入机制**：`write_user_task_context_markdown` 自动为每个用户生成 `AI_TASK_CONTEXT.md`，Claude CLI 启动时可读取

### 3.2 核心问题

#### 问题 1：任务助手是"假 AI"

`ai_task_assistant_service.py` 的核心逻辑是 Python 正则匹配，不是 LLM 调用：

```python
# 实际代码
def _infer_task_type(text: str) -> str:
    if re.search(r"联调|协同|验证|对接|测试|系统", text):
        return "系统联调任务"
    if re.search(r"方案|设计|架构|规划|评审|调研", text):
        return "方案设计任务"
    return "开发实现任务"
```

这意味着：
- 无法理解复杂多句描述
- 无法做多轮上下文推理
- 草稿质量上限极低（正则匹配天花板）
- 给用户的"AI 助理"体验名不副实

**影响**：这是该功能目前最大的真实性风险——用户以为在和 AI 对话，实际只是关键词匹配。

#### 问题 2：两条 AI 线割裂

```
线路 A: 前端聊天 UI → Flask API → Python 规则引擎（假 AI）
线路 B: 前端 iframe  → ttyd  → Claude CLI（真 AI）
```

两条线路完全没有数据互通：
- Chat UI 里的草稿不会自动同步到 ttyd 终端
- ttyd 终端里的对话结果不会回填到前端的任务草稿面板
- 用户需要手动在两个界面间复制粘贴

#### 问题 3：ttyd 终端体验粗糙

- 模型选择在终端菜单里，用户需要理解命令行操作
- 没有对话历史持久化（进程退出即丢失）
- 前端无法感知 Claude 在终端里的执行状态
- 创建的任务单不会自动回显到前端页面
- 需要用户手动在 Claude CLI 里操作，而非引导式交互

#### 问题 4：AI Insights 是静态 Mock

`mock/platformData.js` 中的 4 条 AI 建议是写死的字符串，不会根据实际数据变化。前端的"开始分析"按钮只是把草稿文本拼接到固定文案里：

```jsx
content: analysisInput
  ? `${item.content} 当前分析基于草稿重点："${analysisInput.slice(0, 36)}..."。`
  : item.content,
```

#### 问题 5：缺少流式响应

所有 AI API 都是 request-response 模式，对话消息需要等待完整回复。对于真正接入 LLM 后的体验，缺少 SSE 或 WebSocket 流式输出能力。

#### 问题 6：可观测性空白

- ttyd 会话有基本的日志记录（`ai_debug_subprocess.log`）
- 但没有 LLM token 用量统计、成本追踪、错误率监控
- 没有用户行为分析（哪些 AI 能力被使用、使用频率、成功率）

---

## 四、改进建议

### 4.1 短期（1-2 周，快速见效）

#### 建议 1：将任务助手接入真实 LLM

**当前**：Python 正则推断 → 结构化草稿
**改进**：Python 正则推断 → 保留为 fallback → 优先调用 LLM API 生成草稿

具体做法：
```python
# 新增：调用 one-api 的 Chat Completions 接口
def _ai_infer_draft(user_message: str, task_context: str) -> dict:
    response = requests.post(
        f"{one_api_base}/v1/chat/completions",
        json={
            "model": "MiniMax-M2.7",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},  # 注入 project_memory 规则
                {"role": "user", "content": f"任务上下文：{task_context}\n\n用户输入：{user_message}"}
            ],
            "response_format": {"type": "json_object"},  # 结构化输出
        }
    )
    return response.json()["choices"][0]["message"]["content"]
```

**收益**：用最小的改动让"AI 助理"名副其实，前端 UI 和数据契约都不需要变。

#### 建议 2：串联 Chat UI 和 ttyd 终端

- 前端 Chat 中生成的草稿，作为上下文自动注入到 ttyd 工作区的 `CLAUDE.md` 中
- ttyd 终端中 Claude 的产出，通过约定格式的文件回写到前端可读取的 JSON

### 4.2 中期（2-4 周，架构升级）

#### 建议 3：AI Insights 从静态 Mock 升级为真实分析

**方案**：
1. 后端新增 `services/ai_insight_service.py`，读取 DB 中的真实工时和绩效数据
2. 用 LLM 对数据做分析，按 `project_memory/task_analysis_rules.md` 中定义的输出结构（summary / metrics / risks / suggestions / evidence）生成
3. 支持定期刷新 + 缓存，避免每次请求都调用 LLM
4. 前端"开始分析"按钮触发真正的后端 LLM 分析

#### 建议 4：引入流式响应

- 后端 API 增加 SSE 支持（`text/event-stream`）
- 前端用 `EventSource` 或 `fetch` + `ReadableStream` 消费流式数据
- 对话消息逐字呈现，提升交互感

#### 建议 5：增加 LLM 可观测性

- 记录每次 LLM 调用的 token 用量、模型、延迟、成本
- 增加 `ai_usage` 数据库表，按用户/日期/模型汇总
- 简单的 Grafana 面板或管理后台的统计页面

### 4.3 长期（1-3 个月，Agent 化演进）

#### 建议 6：从"对话"升级为"Agent"

当前系统可以定义一个 Agent 工作流：

```
用户说"帮我创建下周三的联调任务"
  → Agent 理解意图
  → Agent 查询 DB 中用户当前负载
  → Agent 分析时间可行性
  → Agent 生成草稿
  → Agent 展示草稿给用户确认
  → Agent 调用 Teambition API 创建任务
  → Agent 返回任务链接和摘要
```

实现路径：
1. 使用 Anthropic SDK 的 `tool_use` 能力，定义工具集：`query_my_tasks`、`create_task_draft`、`create_teambition_task`
2. 用 LangGraph 或简单的 ReAct 循环编排多步执行
3. 保留 Human-in-the-Loop 确认节点（根据 `project_memory` 规则，创建任务前必须确认）

#### 建议 7：MCP Server 化

将系统核心能力封装为 MCP Server：
- **工具**：`query_tasks`、`query_hours`、`query_performance`、`create_task`
- **资源**：`task_context://current_user`、`team_overview://nav_team`
- **提示**：任务分析模板、周报生成模板

**收益**：
- Claude CLI 可直接通过 MCP 调用这些工具，代替当前"写入 Markdown 文件让 AI 读取"的间接方式
- 其他 AI 应用（Claude Desktop、Cursor、Windsurf 等）也可以接入
- 工具逻辑只需维护一份

#### 建议 8：统一 AI 体验

终极目标是**合并两条 AI 线路**：

```
当前（分裂）:
  Chat UI (假AI) ←→ Flask API ← 规则引擎
  ttyd iframe (真AI) ←→ Claude CLI

未来（统一）:
  Chat UI ←→ Flask API ←→ Agent 编排层 ←→ LLM (one-api)
                                    ↓
                              MCP Tools → DB / Teambition API / 文件系统
                                    ↓
                              ttyd (高级模式，可选)
```

前端 Chat UI 作为主入口，ttyd 作为高级模式的可选降级，两者共享同一套 Agent 工具层。

---

## 五、技术选型建议

| 需求 | 推荐方案 | 理由 |
| --- | --- | --- |
| LLM 接入 | 继续使用 one-api 网关 + Anthropic SDK (Python) | 已有机房部署，模型切换方便 |
| 对话管理 | 自建轻量级（当前 JSON 文件方案已可用，后续可迁到 SQLite） | 需求明确，无需引入 LangChain |
| Agent 编排 | Anthropic SDK 原生 tool_use + 自建 ReAct 循环 | 轻量、可控、不引入框架依赖 |
| 流式响应 | Flask SSE + 前端 EventSource | 简单直接，无需 WebSocket |
| 工具标准化 | MCP (Model Context Protocol) | 未来可被其他 AI 应用复用 |
| 可观测性 | 自建 `ai_usage` 表 + 结构化日志 | 需求简单，不急于引入 LangSmith |
| 数据库查询 (RAG) | 当前 SQLAlchemy 直接查询（规则化检索），暂不引入向量数据库 | 数据规模小，结构化查询已够用 |
| 前端 AI SDK | 当前自建 `api/dashboard.js` 已够用，如需增强可考虑 Vercel AI SDK (`useChat`) | 渐进式引入 |

**不推荐在当前阶段引入的**：
- **LangChain/LangGraph**：当前需求用一个简单的 `tool_use` 循环即可满足，引入框架增加复杂度且不利于调试
- **向量数据库 (Pinecone/Weaviate)**：当前任务数据已完全结构化，直接 SQL 查询比语义搜索更准确
- **CrewAI/AutoGen**：当前没有多 Agent 协作的场景，单 Agent 足够

---

## 六、优先路线图

```
Phase 1 (本周) ──────────────────────────────────────────
  任务助手接入真实 LLM（替换正则推断）
  → 用户真正体验到 AI 对话

Phase 2 (下周) ──────────────────────────────────────────
  AI Insights 真实化（读取 DB，LLM 生成分析）
  Chat 与 ttyd 终端串联（草稿双向同步）
  → AI 分析页不再是静态文字

Phase 3 (两周后) ────────────────────────────────────────
  流式响应（SSE）
  可观测性基础（token 用量统计）
  → 体验和运维就绪

Phase 4 (一个月后) ──────────────────────────────────────
  Agent 工作流（tool_use + 多步推理）
  Human-in-the-Loop 确认节点
  → 用户一句话创建任务成为现实

Phase 5 (按需) ─────────────────────────────────────────
  MCP Server 化
  多 Agent 协作（如审批流）
  → 对外开放 AI 能力
```

---

## 七、结论

management-system 的 AI 功能已经有了一个**骨架完整但血肉不足**的起点：

- **做对了的**：ttyd 终端方案务实快速、多用户隔离设计合理、规则文档化便于维护、多模型网关灵活
- **需要补的**：任务助手的"假 AI"问题必须优先解决、Chat 和终端两条线需要打通、AI Insights 需要从静态数据变为真实分析
- **可以演进的**：从嵌入式终端 → Chat API → Agent 工作流 → MCP 工具化，是一条清晰的渐进路线

核心原则：**先让 AI 真正"AI 起来"，再让 AI"Agent 起来"，最后让 AI"开放出来"**。
