# MCP Server 设计（tbcreate + 任务分析）

> 最后更新: 2026-06-02

## 1. 核心思路

### 1.1 从"操作手册"到"原生的 AI 能力"

当前 ttyd 模式的做法：

```
Claude CLI 启动 → 读 CLAUDE.md（操作手册）→ 读 SKILL.md（流程规范）
  → 一问一答收集信息 → 写 draft.json → curl 通知后端
```

本质是**给 Claude 发了一份 .txt 操作手册**，告诉它"你按这个流程做"。问题是手册占 token、curl 易出错、流程僵化。

MCP 模式的做法：

```
AI 终端工具(Claude Code/Cursor) 连接 MCP Server
  → MCP Server 提供三种能力：
    1. Resources — 领域知识（TB 规则、格式规范）→ AI "学会"这个领域
    2. Prompts  — 系统提示词（你的角色是 TB 创建助手）→ AI "知道"自己该干什么
    3. Tools    — 可执行操作（查上下文、存草稿、创建任务）→ AI "能干"这些事
  → AI 综合这三种能力，自主决策怎么创建 TB 单
```

**核心差异**：ttyd 模式是"AI 按手册执行"，MCP 模式是"AI 理解了领域，自己能决定怎么做"。

### 1.2 三个 MCP 能力与现有内容的映射

| MCP 能力 | 现有对应物 | 在哪 |
|----------|-----------|------|
| **Resources** | tb_rule.md（字段规范、参与度档位、校验规则）、work_hour.md（工时分类与判定） | `ai/domain/` |
| **Prompts** | 2_tb_create/SKILL.md（"你是任务创建助手…"）、1_tb_analysis/SKILL.md（分析指令） | `ai/skills/` |
| **Tools** | Flask REST API + Claude CLI 的 curl 调用 | `ai/tbcreate/routes.py` `ai/teambition/service.py` |

---

## 2. 拆解前（现状）

### 2.1 tbcreate 链路

```
用户(Web) → POST /ai/ttyd/session → ttyd 子进程 → Claude CLI
  → Claude 读 CLAUDE.md + AI_TASK_CONTEXT.md（文件）
  → 一问一答收集信息
  → 写 draft.json
  → curl 通知 /draft/notify → SSE 推前端
  → 用户确认 → POST /ai/create_teambition → 钉钉 API
```

问题：

- 强依赖 ttyd 二进制（部署环境限制）
- Claude 通过写文件和 curl 与后端通信，链路脆弱
- prompt 指令（SKILL.md / CLAUDE.md）占据大量上下文 token
- 规则和操作耦合在 prompt 里 — 改规则要改 prompt，没法独立维护
- 用户必须在 Web 终端打字交互，不能离线异步处理

### 2.2 task_analysis 链路

```
前端 → POST /ai/task-analysis/fetch-tasks → 展示数据
     → POST /ai/task-analysis/search-kb   → 展示检索结果
     → POST /ai/task-analysis/generate-report → LLM 分析 → 展示报告
```

问题：

- 三步必须由前端顺序调用，不能在 AI 对话中自然触发
- 分析结果无法与后续工单创建串联

---

## 3. MCP 化后架构

### 3.1 AI 视角：连接即"学会"

```
┌──────────────────────────────────────────────────────────┐
│  Claude Code / Cursor / Claude Desktop                   │
│                                                          │
│  启动时自动连接 MCP Server，拉取：                        │
│                                                          │
│  📖 Resources（领域知识）→ "TB 单是什么、有哪些规则"      │
│  💬 Prompts（系统提示）  → "我是 TB 创建助手，我知道流程"  │
│  🔧 Tools（可执行操作）  → "我能查数据、存草稿、创建任务"  │
│                                                          │
│  然后用户说一句"创建个托盘识别的优化任务"，                │
│  AI 自己就知道该怎么做：                                  │
│    1. 调 get_user_task_context 看当前任务                │
│    2. 调 search_knowledge_base 查相关知识                │
│    3. 按 TB 规范生成草稿 → 调 save_task_draft            │
│    4. 用户确认 → 调 create_teambition_task               │
└──────────────────────────────────────────────────────────┘
         │
         │ MCP Protocol (stdio / SSE)
         ▼
┌──────────────────────────────────────────────────────────┐
│                     MCP Server (新增)                     │
│                                                          │
│  Resources:         Prompts:           Tools:            │
│  tb-task-spec       tb-create-prompt   get_user_ctx       │
│  tb-work-hour        tb-analyze-prompt  save_draft         │
│                                         create_task        │
│                                         analyze_tasks      │
│                                         search_kb          │
└──────────┬───────────────────────────────────────────────┘
           │ 复用现有 Service 层（不改动）
           ▼
┌──────────────────────────────────────┐
│  context.py / service.py / data.py   │
│  retriever / ORM / 钉钉 API          │
└──────────────────────────────────────┘
```

### 3.2 模块路径

```
backend/ai/mcp/
├── __init__.py             # main(): 启动入口
├── server.py               # FastMCP 实例，注册 Resources + Prompts + Tools
├── resources/
│   └── rules.py            # 注册 TB 规则相关的 Resources
├── prompts/
│   └── tb_prompts.py       # 注册系统级 Prompts
├── tools/
│   ├── __init__.py
│   ├── task_context.py     # get_user_task_context
│   ├── parent_tasks.py     # get_parent_tasks
│   ├── draft.py            # save_task_draft / get_task_draft
│   ├── task_create.py      # create_teambition_task
│   ├── analysis.py         # analyze_tasks
│   └── kb_search.py        # search_knowledge_base
└── transport.py            # stdio / SSE 选择逻辑
```

启动方式（独立进程）：

```bash
# stdio 模式（Claude Desktop / Claude Code）
python -m ai.mcp

# SSE 模式（远程客户端）
python -m ai.mcp --transport sse --port 5100
```

---

## 4. Resources 设计 — AI 的"领域知识库"

### 4.1 设计原则

Resources 是只读内容，对应 `ai/domain/` 下的纯领域知识文件。AI 客户端在需要时主动读取。好处：

- **按需加载**：不占初始上下文，AI 在需要时自己调用 `read_resource`
- **独立维护**：规则改了就改 domain 文件，不影响 Tool/Prompt
- **纯知识分离**：domain/ 只管"是什么"，skills/ 管"怎么做"

### 4.2 Resource 清单

只有 2 个 Resource，都和 `ai/domain/` 一一对应：

| URI | 内容 | 来源 |
|-----|------|------|
| `rule://tb/task-spec` | TB 任务单字段规范、参与度档位 [0.2, 0.5, 1, 1.5, 2, 2.5, 3]、钉钉 customField ID、校验规则 | `ai/domain/tb_rule.md` |
| `rule://tb/work-hour` | TB 有效工时三类（指派型/自主型/能力型）的定义、占比建议、AI 判定指引 | `ai/domain/work_hour.md` |

### 4.3 Resource 内容示例

**`rule://tb/task-spec`** — TB 任务单规范（`ai/domain/tb_rule.md`）：

```markdown
# TB 任务单规范

## 参与度档位（固定）
[0.2, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0] 人天

## 产出格式
- 每项产出格式："具体描述(N天)", N 为小数
- 所有产出天数之和 = 参与度，必须落在上述档位之中
- 参与度 = sum(产出天数)，AI 不需要手动指定

## 字段校验规则
1. title ≤ 18 中文字符
2. workType ∈ {指派型, 自主型, 能力型}
3. participationLevel = sum(outputs 天数) 且必须在档位中
4. startDate ≤ dueDate
```

**`rule://tb/work-hour`** — TB 工时分类与判定（`ai/domain/work_hour.md`）：

```markdown
# TB 有效工时分类

## 指派型工时
- 定义：主管下发的项目研发/客户问题/紧急支持
- 特征：需求来自外部（主管、客户、跨部门），被动接受
- 占比建议：50-70%

## 自主型工时
- 定义：基于实际问题的主动改进，必须有可复用产出物
- 特征：自己发现问题，自己设计解决方案，有文档/工具/规范等可复用产出
- 占比建议：25-35%

## 能力型工时
- 定义：学习/调研/分享，必须形成知识沉淀
- 特征：以学习为目的，产出物为文档/分享/代码仓库等可传播内容
- 上限：10-15%
```

### 4.4 Resource 注册

```python
# ai/mcp/resources/rules.py

_DOMAIN_DIR = Path(__file__).resolve().parent.parent.parent / "domain"


def register_resources(mcp):
    """注册所有 TB 领域知识 Resources。"""

    @mcp.resource("rule://tb/task-spec")
    def get_task_spec() -> str:
        """TB 任务单字段规范、参与度档位、校验规则。"""
        return (_DOMAIN_DIR / "tb_rule.md").read_text(encoding="utf-8")

    @mcp.resource("rule://tb/work-hour")
    def get_work_hour_rules() -> str:
        """TB 有效工时分类定义、占比建议、AI 判定指引。"""
        return (_DOMAIN_DIR / "work_hour.md").read_text(encoding="utf-8")
```

---

## 5. Prompts 设计 — AI 的"角色认知"

### 5.1 设计原则

Prompts 是模板化的提示词，告诉 AI **它是谁、它要做什么、它能用什么**。相比于 Resources（知识），Prompts 更偏向"行动指引"。

### 5.2 Prompt 清单

| 名称 | 用途 | 参数 |
|------|------|------|
| `tb-create` | TB 工单创建助手 | `user_name`（用户姓名） |
| `tb-analyze` | TB 任务分析助手 | `quarter`（季度，可选） |

### 5.3 tb-create Prompt

```markdown
你是 Teambition 任务创建助手，用户叫 {user_name}。

## 你的能力

你可以通过调用 Tools 完成以下操作：
- 查询用户当前的任务上下文
- 检索知识库中的技术文档和规范
- 保存任务草稿（用户可在 Web 面板看到）
- 用户确认后，正式创建 Teambition 任务

## 创建 TB 单的流程

1. **了解上下文**：先调用 get_user_task_context 查看用户当前任务情况
2. **按需检索**：如果涉及具体技术领域，调用 search_knowledge_base
3. **收集信息**：与用户对话，一问一答收集以下信息：
   - 任务标题（≤18字）
   - 工时类型（指派型/自主型/能力型）
   - 任务背景和目标
   - 任务产出（每项格式：描述(N天)）
   - 起止时间
4. **生成草稿**：信息收集完毕后，调用 save_task_draft
5. **等待确认**：展示草稿摘要，等待用户确认
6. **创建任务**：用户确认后，调用 create_teambition_task

## 重要规则

- **参与度** = 所有产出天数之和，必须落在 [0.2, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0] 之中
- **标题**不超过 18 个中文字符
- 产出格式严格为 "描述(N天)"
- 创建真实任务前，必须让用户确认草稿
- 如果 save_task_draft 返回 validation.warnings，必须告知用户并调整

## 关于规则的更多细节

如需了解 TB 工时分类的详细定义、字段规范的完整内容，请阅读以下 Resources：
- rule://tb/task-spec — 字段规范、参与度档位、校验规则
- rule://tb/work-hour — 工时分类定义与判定标准
```

### 5.4 tb-analyze Prompt

```markdown
你是企业任务分析专家，帮助用户分析季度任务数据。

## 分析维度

调用 analyze_tasks Tool 后，你会得到结构化的分析报告，包含：
1. 需求雷达 — 基于用户任务提取技术关键词，给出存量挖掘/质量升维/前瞻探索建议
2. 自主型建议 — 从现有任务中发现可转化为自主型工时的改进点
3. 能力型建议 — 识别技术方向空白，给出学习建议
4. 任务风险分析 — 工时分布对标、风险预警、建议任务草案

## 后续动作

如果分析报告中包含 draft_tasks（建议任务草案），你可以：
- 与用户讨论哪些建议值得创建
- 使用 tb-create 流程创建选定的任务
```

### 5.5 Prompt 注册

```python
# ai/mcp/prompts/tb_prompts.py

def register_prompts(mcp):
    """注册 TB 相关的系统 Prompts。"""

    @mcp.prompt()
    def tb_create(user_name: str = "用户") -> str:
        return f"""你是 Teambition 任务创建助手，用户叫 {user_name}。

## 你的能力

你可以通过调用 Tools 完成以下操作：
- 查询用户当前的任务上下文
- 检索知识库中的技术文档和规范
- 保存任务草稿（用户可在 Web 面板看到）
- 用户确认后，正式创建 Teambition 任务

## 创建 TB 单的流程

1. **了解上下文**：先调用 get_user_task_context 查看用户当前任务情况
2. **按需检索**：如果涉及具体技术领域，调用 search_knowledge_base
3. **收集信息**：与用户对话，收集以下信息（每次只问一个问题）：
   - 任务标题（≤18字）
   - 工时类型（指派型/自主型/能力型）
   - 任务背景和目标
   - 任务产出（每项格式：描述(N天)）
   - 起止时间
4. **生成草稿**：信息收集完毕后，调用 save_task_draft
5. **等待确认**：展示草稿摘要，等待用户确认
6. **创建任务**：用户确认后，调用 create_teambition_task

## 重要规则

- **参与度** = 所有产出天数之和。必须落在 [0.2, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0] 之中
- **标题**不超过 18 个中文字符
- 产出格式严格为 "描述(N天)"
- 创建真实任务前，必须让用户确认草稿
- 如果 save_task_draft 返回 validation.warnings，必须告知用户并调整

## 关于规则的更多细节

如需了解 TB 工时分类的详细定义、字段规范的完整内容，可阅读 Resources：
- rule://tb/task-spec — 字段规范、参与度档位、校验规则
- rule://tb/work-hour — 工时分类定义与判定标准
"""

    @mcp.prompt()
    def tb_analyze(quarter: str = "") -> str:
        quarter_info = f"\n当前分析季度：{quarter}" if quarter else ""
        return f"""你是企业任务分析专家。{quarter_info}

## 分析维度

调用 analyze_tasks Tool 后，你会得到结构化的分析报告，包含：
1. 需求雷达
2. 自主型建议
3. 能力型建议
4. 任务风险分析

## 后续动作

如果分析报告中包含 draft_tasks（建议任务草案），可以主动询问用户是否要创建。
"""
```

---

## 6. Tools 设计 — AI 的"可执行操作"

### 6.1 Tool 总览

| Tool | 用途 | 调用时机 |
|------|------|---------|
| `get_user_task_context` | 获取用户当前全部任务数据 | 开始创建前，了解用户任务全景 |
| `get_parent_tasks` | 获取可选父任务列表 | 用户需要指定父任务时 |
| `save_task_draft` | 保存任务草稿 + 校验 | 信息收集完毕，生成草稿 |
| `get_task_draft` | 读取当前草稿 | 恢复之前的草稿状态 |
| `create_teambition_task` | 正式创建 TB 任务 | 用户确认草稿后 |
| `analyze_tasks` | 多维任务分析 | 用户要求分析季度任务时 |
| `search_knowledge_base` | 语义检索知识库 | 需要了解具体技术背景时 |

### 6.2 save_task_draft — 核心 Tool

注意：AI 不需要自己算参与度，后端自动校验并修正。

```json
// Input
{
  "title": "优化托盘识别精度",
  "workType": "自主型",
  "requirementDesc": "背景：托盘识别在光照不足时误检率高\n目标：将误检率从 15% 降至 5%",
  "outputs": [
    "数据增强与模型重训(1.0天)",
    "边界 case 测试集构建(0.5天)"
  ],
  "startDate": "2026-06-03T00:00:00+08:00",
  "dueDate": "2026-06-30T23:59:59+08:00",
  "parentTaskId": ""
}

// Output
{
  "saved": true,
  "draft": {
    "title": "优化托盘识别精度",
    "workType": "自主型",
    "participationLevel": 1.5,   // ← 后端自动计算
    ...
  },
  "validation": {
    "valid": true,
    "participationLevel": 1.5,
    "tierMatch": true,
    "warnings": [],
    "errors": []
  }
}
```

**后端自动校验的内容**（AI 不需要操心）：

| 校验项 | 规则 | 后端行为 |
|--------|------|---------|
| 标题长度 | ≤ 18 中文字符 | 超长 → `validation.warnings` 中提示 |
| workType | 必须是三选一 | 非法 → `validation.valid=false` |
| 参与度 = sum(outputs 天数) | 自动计算 | 不一致 → 以 sum 为准，warnings 提示 |
| 参与度档位 | [0.2,0.5,1,1.5,2,2.5,3] | 不在档位 → warnings 提示 |
| 日期逻辑 | startDate ≤ dueDate | 非法 → warnings 提示 |
| 日期格式 | ISO 8601 | 非法 → errors |

### 6.3 create_teambition_task — 安全边界

```json
// Input — 直接传 draft 对象
{
  "title": "...",
  "workType": "...",
  "requirementDesc": "...",
  "outputs": [...],
  "participationLevel": 1.5,
  "startDate": "2026-06-03T00:00:00+08:00",
  "dueDate": "2026-06-30T23:59:59+08:00",
  "parentTaskId": ""
}

// Output
{
  "success": true,
  "taskId": "694a3c1d...",
  "taskUrl": "https://www.teambition.com/task/694a3c1d...",
  "message": "任务已创建"
}
```

**安全约束**：
- `executorId` 从环境变量 `MCP_USER_ID` 注入，Tool input 不接受此参数
- 创建前自动走一遍 `validate_draft` 校验
- 失败返回结构化错误（而非 curl 的模糊报错）

### 6.4 其余 Tools 简要

- **get_user_task_context** — 无参数输入，返回用户全部任务的 JSON（任务列表 + 指标汇总 + 父子关系树）
- **get_parent_tasks** — 可选 `keyword` 过滤，返回可选的父任务列表
- **get_task_draft** — 无参数，返回当前 draft.json 内容或空草稿
- **analyze_tasks** — 可选 `quarter` / `project_ids`，一步完成"拉数据→搜知识库→LLM 分析"
- **search_knowledge_base** — `query` + `top_k`，返回知识库 chunk 列表

---

## 7. Server 组装

```python
# ai/mcp/server.py

from mcp.server.fastmcp import FastMCP
from .resources.rules import register_resources
from .prompts.tb_prompts import register_prompts
from .tools import (
    task_context, parent_tasks, draft, task_create, analysis, kb_search,
)

mcp = FastMCP("tb-mcp")


def create_server(user_id: str, user_name: str):
    """创建 MCP Server 实例，注入用户身份。"""

    # ── 1. 注册 Resources（领域知识） ──
    register_resources(mcp)

    # ── 2. 注册 Prompts（系统指令） ──
    register_prompts(mcp)

    # ── 3. 注册 Tools（可执行操作） ──
    @mcp.tool()
    async def get_user_task_context() -> dict:
        """获取当前用户的所有任务上下文。在创建 TB 单前先调用此 Tool 了解任务全景。"""
        return task_context.get_user_task_context(user_id, user_name)

    @mcp.tool()
    async def get_parent_tasks(keyword: str = "") -> dict:
        """获取可作为父任务的任务列表。可按 keyword 过滤标题。"""
        return parent_tasks.get_parent_tasks(user_id, keyword)

    @mcp.tool()
    async def save_task_draft(
        title: str,
        work_type: str,
        requirement_desc: str,
        outputs: list[str],
        start_date: str,
        due_date: str,
        parent_task_id: str = "",
    ) -> dict:
        """保存 TB 任务草稿。后端自动校验参与度档位、标题长度等。"""
        return draft.save_task_draft(
            owner_key=user_id,
            title=title,
            work_type=work_type,
            requirement_desc=requirement_desc,
            outputs=outputs,
            start_date=start_date,
            due_date=due_date,
            parent_task_id=parent_task_id,
        )

    @mcp.tool()
    async def get_task_draft() -> dict:
        """读取当前保存的任务草稿。"""
        return draft.get_task_draft(user_id)

    @mcp.tool()
    async def create_teambition_task(
        title: str, work_type: str, requirement_desc: str,
        outputs: list[str], participation_level: float,
        start_date: str, due_date: str, parent_task_id: str = "",
    ) -> dict:
        """正式创建 Teambition 任务。调用前请确保用户已确认草稿内容。"""
        draft_data = {
            "title": title, "workType": work_type,
            "requirementDesc": requirement_desc, "outputs": outputs,
            "participationLevel": participation_level,
            "startDate": start_date, "dueDate": due_date,
            "parentTaskId": parent_task_id, "executorId": user_id,
        }
        return task_create.create_teambition_task(draft_data)

    @mcp.tool()
    async def analyze_tasks(quarter: str = "") -> dict:
        """多维任务分析。返回需求雷达、自主型/能力型建议、风险分析及建议任务草案。"""
        return analysis.analyze_tasks(user_id, quarter)

    @mcp.tool()
    async def search_knowledge_base(query: str, top_k: int = 10) -> dict:
        """在知识库中语义检索相关技术文档。"""
        return kb_search.search(query, top_k)

    return mcp
```

---

## 8. 完整交互流程

### 8.1 AI 终端启动时

```
1. Claude Code 读取 .mcp.json 配置 →
2. 启动 python -m ai.mcp 子进程 →
3. MCP Server 注册 Resources + Prompts + Tools →
4. Claude Code 得知：
   - 有 2 个 Resources 可读（TB 字段规范、工时分类）
   - 有 2 个 Prompts 可用（tb-create / tb-analyze）
   - 有 7 个 Tools 可调用
```

### 8.2 用户创建 TB 单

```
用户: 帮我创建一个任务，优化托盘识别的精度问题

Claude Code: [内部决策：需要了解当前任务全景]
  → 调用 get_user_task_context()
  ← 返回：53 个任务，2 个逾期，当前无托盘识别相关任务

Claude Code: [内部决策：需要了解托盘识别技术背景]
  → 调用 search_knowledge_base(query="托盘识别 精度优化")
  ← 返回：YOLOv8 模型文档、训练数据 5000 张、误检率基准

Claude Code:
  你的当前状态：53 个任务，18 个未完成。没有托盘识别相关的进行中任务。
  
  知识库显示当前托盘识别基于 YOLOv8，训练数据 5000 张。
  
  我先确认几个信息：
  1. 这个任务是优化现有模型，还是从零开始？

用户: 现有模型优化，目标是误检率从 15% 降到 5% 以下

Claude Code:
  明白了。这是**自主型**工时（基于实际问题的改进）。
  
  建议任务产出：
  1. 数据增强与模型重训(1.0天)
  2. 边界 case 测试集构建(0.5天)
  3. A/B 测试与上线验证(0.5天)
  
  参与度合计 2.0 人天 ✓（在标准档位中）
  
  开始日期和截止日期怎么设？

用户: 明天开始，月底截止

Claude Code:
  → 调用 save_task_draft(title="优化托盘识别精度", work_type="自主型", ...)
  ← 返回：{"saved": true, "validation": {"valid": true, "warnings": []}}

Claude Code:
  草稿已保存：
  | 字段 | 值 |
  |------|-----|
  | 标题 | 优化托盘识别精度 |
  | 类型 | 自主型 |
  | 产出 | 3 项，合计 2.0 人天 ✓ |
  | 日期 | 2026-06-03 ~ 2026-06-30 |
  
  确认无误的话，我帮你正式创建？

用户: 确认

Claude Code:
  → 调用 create_teambition_task(...)
  ← 返回：{"success": true, "taskId": "694a3c1d...", "taskUrl": "https://..."}

Claude Code:
  ✅ 已创建！任务 ID 694a3c1d，链接：https://www.teambition.com/task/694a3c1d
```

### 8.3 分析 → 创建闭环

```
用户: 分析一下这季度任务

Claude Code:
  → 调用 analyze_tasks(quarter="2026Q2")
  ← 返回：工时分布 指派型 35.8% | 自主型 11.3% | 能力型 0%
         ⚠️ 自主型严重不足
         draft_tasks: [托盘识别误检率优化(1.5天), 导航模块规范梳理(1.0天)]

Claude Code:
  📊 Q2 分析：自主型工时偏低（11.3% vs 建议 25-30%），有"结构性平庸"风险。
  
  建议创建以下改进任务：
  1. 托盘识别误检率优化（自主型，1.5 人天）
  2. 导航模块代码规范梳理（自主型，1.0 人天）
  
  要创建哪几个？

用户: 第一个

Claude Code:
  [自动按照 tb-create 流程，补全产出、日期等字段]
  → save_task_draft → 展示草稿 → 等待确认 → create_teambition_task
  ✅ 已创建！
```

---

## 9. 与现有系统的共存

### 9.1 draft.json 共享

```
runtime/users/{owner_safe}/workspaces/default/draft.json
```

MCP `save_task_draft` 和 ttyd Claude CLI 写入**同一个文件**。Web 前端面板始终展示最新版本。

### 9.2 冲突处理

- 无论哪种模式写入，都会触发 SSE 通知 → 前端刷新
- 后写覆盖先写，前端以最后一次 SSE 为准

### 9.3 职责分工

| 能力 | MCP Server | ttyd + Claude CLI |
|------|-----------|-------------------|
| 领域知识 | Resources（按需读取） | CLAUDE.md / SKILL.md（启动即全量加载） |
| 系统指令 | Prompts（模板化） | CLAUDE.md 内嵌 |
| 数据获取 | Tool 调用 | 读 AI_TASK_CONTEXT.md 文件 |
| 草稿写入 | `save_task_draft` Tool | 写 draft.json + curl 通知 |
| 任务创建 | `create_teambition_task` Tool | 用户在 Web 面板点击确认 |

---

## 10. 安全设计

- `user_id` 通过 `MCP_USER_ID` 环境变量注入，Tool 参数不可覆盖
- `create_teambition_task` 的 `executorId` 强制使用注入的 `user_id`
- Phase 1 仅开放读/写草稿 + 创建任务，不开放修改/删除已有任务
- API Key 从 `ai/config.json` 读取，不通过任何 MCP 通道暴露

---

## 11. 实施计划

### Phase 1（1-2 天）— MCP Server 骨架 + Resources + Prompt + 核心 Tool

- [ ] 安装 `mcp` SDK，搭建 `FastMCP` 实例
- [ ] 注册 2 个 Resources（TB 字段规范 `domain/tb_rule.md`、工时分类 `domain/work_hour.md`）
- [ ] 注册 `tb-create` Prompt（系统提示词）
- [ ] 实现 `get_user_task_context` + `save_task_draft` + `create_teambition_task` Tools
- [ ] 在 Claude Code 中跑通完整创建流程

### Phase 2（1 天）— 分析闭环 + 知识库检索

- [ ] 实现 `analyze_tasks` Tool
- [ ] 实现 `search_knowledge_base` Tool
- [ ] 注册 `tb-analyze` Prompt
- [ ] 跑通 分析 → draft_tasks → save_draft → create 闭环

### Phase 3（按需）— SSE transport + Web 面板联动

- [ ] SSE transport 支持
- [ ] Web 前端面板实时同步（已有 SSE 通道自动兼容）

---

## 12. 一句话结论

**MCP 的本质不是暴露 API，而是让 AI "学会"一个领域。通过 Resources 灌规则、Prompts 定角色、Tools 给能力，AI 连接 MCP Server 后自己就知道怎么创建 TB 单 — 不需要操作手册，不需要 ttyd，不需要 curl。**
