# rules / skills 清理方案

> 最后更新: 2026-06-02

## 1. 问题诊断

### 1.1 现状文件清单

```
ai/
├── rules/
│   ├── data_contracts.md           ← 过时 API 文档，引用的路由大多已废弃
│   └── task_ticket.md              ← TB 创建规则（与 SKILL.md 80% 重叠）
│
├── skills/
│   ├── tbcreate/SKILL.md           ← TB 创建流程指令（与 task_ticket.md + workspace.py 重叠）
│   ├── task-analysis/SKILL.md      ← 任务分析 prompt 模板 ✅ 正常使用
│   ├── task-analysis/tb_rule.md    ← 工时规则（分类错误：不是 skill，是领域知识）
│   └── keyword-extract/SKILL.md    ← 废弃，代码库零引用
│
└── runtime/shared/.claude/skills/  ← ai/skills/ 的完整镜像（手工同步，高风险）
    └── (同上 4 个文件)
```

### 1.2 代码引用分布

| 代码位置 | 引用的文件 | 类型 |
|----------|-----------|------|
| `tbcreate/workspace.py:_claude_md_template()` | 硬编码在函数体内 | **反模式** |
| `tbcreate/workspace.py:init_workspace()` | `ai/rules/task_ticket.md` → 复制到 workspace | 文件复制 |
| `tbcreate/context.py:write_user_task_context_markdown()` | 硬编码 CLAUDE.md 在函数体内 | **反模式** |
| `knowledge/workspace.py:_claude_md_template()` | 硬编码在函数体内 | **反模式** |
| `task_analysis/analysis.py` | `ai/skills/task-analysis/SKILL.md` | 文件读取 |
| `knowledge/dashboard_analysis.py` | `runtime/shared/.claude/skills/task-analysis/SKILL.md` | 文件读取（应指向同一文件） |
| `task_analysis/routes.py` | `ai/skills/keyword-extract/SKILL.md` | 废弃的 LLM 关键词提取 |
| `terminal/launcher.sh` | `runtime/shared/.claude/skills/` → symlink 到 `~/.claude/skills/` | 部署脚本 |

### 1.3 五大病症

| # | 病症 | 表现 |
|---|------|------|
| 1 | **三重冗余** | 同一个"参与度档位"写在 SKILL.md、task_ticket.md、_claude_md_template() 三个地方 |
| 2 | **分类无标准** | tb_rule.md（工时规则）放在 skills/ 目录下，但它是领域知识不是 AI 指令 |
| 3 | **镜像副本** | `ai/skills/` 和 `runtime/shared/.claude/skills/` 手工同步，必有一日不同步 |
| 4 | **硬编码 prompt** | workspace.py 和 context.py 里大段字符串拼接，改规则 = 改代码 |
| 5 | **历史残留** | data_contracts.md（路由已废弃）、keyword-extract/SKILL.md（零引用） |

### 1.4 根因

**没有一个文件分类的心智模型。** 每次加新内容就"放最近的目录"，结果是什么东西都有、什么东西都重复。

---

## 2. 新分类标准

一刀切：按 **"这是什么"** 而不是 **"给谁用"** 分类。

```
┌──────────────────────────────────────────────────────┐
│                                                      │
│   domain/          prompts/          docs/           │
│   ─────────       ──────────        ─────            │
│   领域事实          AI 行为指令       开发者文档        │
│                                                      │
│   "TB 单是什么"    "怎么做 TB 单"    "为什么这么设计"  │
│                                                      │
│   纯知识           流程 + 规则引用   设计决策           │
│   不含指令         不含实现细节      不含运行时代码     │
│   被 prompts 引用  引用 domain 内容  给人类看           │
│                                                      │
└──────────────────────────────────────────────────────┘
```

### 2.1 domain/ — 领域知识

**定义**：关于 TB 任务单的客观事实和约束规则。不包含"你先问什么再问什么"之类的流程指令。

| 内容 | 示例 |
|------|------|
| 字段定义 | draft.json 有哪些字段、类型、必填性 |
| 枚举值 | workType 只能是 指派型/自主型/能力型 |
| 数值约束 | 参与度档位 [0.2, 0.5, 1, 1.5, 2, 2.5, 3] |
| 格式规范 | 标题 ≤ 18 字、产出格式 "描述(N天)" |
| 业务定义 | 什么是指派型工时、什么是自主型工时 |
| ID 映射 | 自定义字段的钉钉 ID |

### 2.2 prompts/ — AI 指令

**定义**：给 AI（无论是 ttyd Claude CLI 还是 MCP Client）的行为指令。描述"怎么做"，引用 domain/ 中的知识。

| 内容 | 示例 |
|------|------|
| 角色定义 | "你是 TB 任务创建助手" |
| 交互流程 | 一问一答顺序、每步问什么 |
| 操作说明 | 先调 get_user_task_context、再调 save_task_draft |
| 行为约束 | 用户确认前不创建真实任务 |
| 输出格式 | 用表格汇总草稿、确认后写入 |

### 2.3 什么是"不再有"的

| 旧分类 | 去向 |
|--------|------|
| `rules/` | 内容拆入 domain/ 或合并入 prompts/ |
| `skills/` | 内容迁入 prompts/ |
| `runtime/shared/.claude/skills/` | 改为从 ai/prompts/ 自动同步 |
| 硬编码在 .py 里的 prompt 字符串 | 改为读文件 |

---

## 3. 新旧文件映射

### 3.1 新目录结构

```
ai/
├── domain/
│   ├── work_hour.md              # 工时分类定义 + 判定标准
│   └── task_spec.md              # TB 单字段规范 + 校验规则
│
├── prompts/
│   ├── tb_create.md              # TB 创建助手指令（给 Claude CLI 和 MCP Prompt）
│   └── tb_analyze.md             # 任务分析 prompt 模板（给 LLM）
│
├── docs/                         # 不变
│
├── scripts/
│   └── install_prompts.sh        # 安装 prompts 到 Claude CLI skills 目录
│
├── rules/          → 删除
├── skills/         → 删除
```

### 3.2 每一行旧内容的去向

```
ai/rules/task_ticket.md ─────────────────────────────┐
  ├─ 草稿必填字段 + 参与度档位 ──► domain/task_spec.md  │ 合并去重
  ├─ 工时类型判断规则 ──────────► domain/work_hour.md  │
  ├─ 需求描述规范化规则 ────────► prompts/tb_create.md  │
  └─ 任务产出生成规则 ──────────► prompts/tb_create.md  │

ai/rules/data_contacts.md ──► 删除（过时 API 文档）     │

ai/skills/tbcreate/SKILL.md ─────────────────────────┤
  ├─ 一问一答流程 ──────────────► prompts/tb_create.md  │ 合并去重
  ├─ draft.json 格式 ───────────► domain/task_spec.md  │
  ├─ 汇总表格展示 ───────────────► prompts/tb_create.md  │
  └─ curl 通知命令 ──────────────► 删除（MCP 不再需要，    │
                                   ttyd 模式改为代码中拼接）│

ai/skills/task-analysis/SKILL.md ─► prompts/tb_analyze.md  (不变，换目录)

ai/skills/task-analysis/tb_rule.md ─► domain/work_hour.md  (内容合并)

ai/skills/keyword-extract/SKILL.md ─► 删除（废弃）

ai/tbcreate/workspace.py:_claude_md_template() ─► 改为读 prompts/tb_create.md
ai/tbcreate/context.py 硬编码 CLAUDE.md ─► 删除，由 workspace.py 统一生成
ai/knowledge/workspace.py:_claude_md_template() ─► 保留（知识库指令独立场景）

runtime/shared/.claude/skills/ ─► 改为 install_prompts.sh 从 ai/prompts/ 同步
```

### 3.3 映射速查表

| 旧文件 | 新位置 | 操作 |
|--------|--------|------|
| `rules/data_contracts.md` | — | **删除** |
| `rules/task_ticket.md` | `domain/task_spec.md` + `domain/work_hour.md` | 拆分合并 |
| `skills/tbcreate/SKILL.md` | `prompts/tb_create.md` | 迁移 + 去重 |
| `skills/task-analysis/SKILL.md` | `prompts/tb_analyze.md` | 迁移 |
| `skills/task-analysis/tb_rule.md` | `domain/work_hour.md` | 合并 |
| `skills/keyword-extract/SKILL.md` | — | **删除** |
| `runtime/shared/.claude/skills/*` | — | 改为同步脚本 |
| `workspace.py` 硬编码 CLAUDE.md | `prompts/tb_create.md` | 改为读文件 |
| `context.py` 硬编码 CLAUDE.md | `prompts/tb_create.md` | 删除重复代码 |

---

## 4. 新文件内容设计

### 4.1 domain/work_hour.md

**来源**：`skills/task-analysis/tb_rule.md`（完整内容）+ `rules/task_ticket.md`（工时类型判断规则部分）

```markdown
# TB 有效工时分类

## 指派型工时

- **定义**：由主管明确下发、以交付为目标的任务工时
- **包括**：项目研发、客户问题、紧急支持
- **占比建议**：50%–60%
- **管理方式**：主管事前分配、事后兜底

## 自主型工时

- **定义**：基于产品/项目/流程中的实际问题，自主识别并推进的改进类工作
- **典型内容**：
  - 产品或项目问题复盘与改进方案
  - 技术债识别、清理与重构
  - 文档缺失补齐、规范梳理
  - 工具脚本、自动化能力建设
  - 性能、稳定性、可靠性优化
  - 研发流程或协作效率改进
- **以下不计入有效工时**：
  - 无明确问题来源或目标
  - 无产出或产出不可复用
  - 低价值重复工作
  - 纯学习但无总结或沉淀
- **认定规则**：必须形成明确可复用的产出物（文档/PR/脚本/报告/方案）
- **管理方式**：主管事后确认，不做事前分配
- **占比建议**：25%–30%

## 能力型工时

- **定义**：用于支撑产品与技术能力提升、避免任务空档的工时
- **包括**：技术学习与笔记、技术分享准备、方案调研、Demo/PoC 验证
- **规则**：学习行为必须形成沉淀（文档/分享/结论），否则不计入；设上限 10%–15%

## AI 判断指引

当需要判断一项任务属于哪种工时类型时：
- 任务主要是学习/调研/分享/PoC/Demo → **能力型**
- 任务是个人的优化/重构/复盘/流程改进/工具补齐 → **自主型**
- 其他正常项目安排或上级安排的任务 → **指派型**
```

### 4.2 domain/task_spec.md

**来源**：`rules/task_ticket.md`（草稿字段部分）+ `skills/tbcreate/SKILL.md`（draft.json 格式部分）

```markdown
# TB 任务单字段规范

## draft.json 完整字段

| 字段 | 类型 | 必填 | 约束 | 说明 |
|------|------|------|------|------|
| title | string | 是 | ≤ 18 中文字符 | 任务标题 |
| workType | string | 是 | 指派型/自主型/能力型 | 工时类型 |
| requirementDesc | string | 是 | 支持 \n 换行 | 需求描述（背景+目标+范围） |
| outputs | string[] | 是 | 每项格式"描述(N天)" | 任务产出清单 |
| participationLevel | float | 是 | 固定档位 | 产出天数之和 |
| dueDate | string | 是 | ISO 8601, 截止日 23:59:59 | 截止日期 |
| startDate | string | 是 | ISO 8601, 开始日 00:00:00 | 开始日期 |
| parentTaskId | string | 否 | taskId 或 "" | 父任务 ID |

## 参与度档位

参与度 = 所有产出天数之和，必须落在以下固定档位中：

**0.2 / 0.5 / 1.0 / 1.5 / 2.0 / 2.5 / 3.0**

- 单个任务参与度原则上不超过 3.0 人天
- 信息不充分时，优先选保守值
- 服务端自动校验并修正，AI 不需要自行计算

## 产出格式

每项产出格式为：`具体描述(N天)`，其中 N 为小数如 1.0、0.5、2.5

产出数量建议 2–5 条，每天至少对应一个可交付的成果。

## 钉钉自定义字段 ID

| 字段名 | 钉钉 customFieldId |
|--------|-------------------|
| 需求描述 | 686273700d15b3f835491a2e |
| 任务性质 | 69d4d037c253ef42e9c31b38 |
| 任务产出 | 6862737e3b781c68b3181925 |
```

### 4.3 prompts/tb_create.md

**来源**：`skills/tbcreate/SKILL.md`（流程指令）+ `rules/task_ticket.md`（规范化规则、产出生成规则）+ `workspace.py:_claude_md_template()`（角色定义）

```markdown
# TB 任务创建助手

你是 TB 任务创建助手，职责是引导用户创建 Teambition 任务草稿。

## 领域知识

在开始前，请了解以下规则（按需查阅）：
- TB 工时分类定义：参考 `domain/work_hour.md`
- TB 任务单字段规范：参考 `domain/task_spec.md`

## 安全规则

- 用户明确确认前，不要写入 draft.json
- 不要调用任何真实的钉钉 API 创建任务
- 所有字段必须按规范填写

## 创建流程

按以下顺序**一问一答**收集信息，每次只问一个问题：

### 1. 任务标题
"请描述一下这个任务的标题（控制在 18 字以内）"

### 2. 工时类型
展示三个选项，让用户回复数字：
```
请选择工时类型：
1) 指派型 — 正常项目/上级安排
2) 自主型 — 个人主动做的优化、复盘等
3) 能力型 — 学习、调研、分享、沉淀
请输入数字 1、2 或 3：
```
**不要替用户选择。** 只展示选项，等待用户回复。

### 3. 任务背景
"这个任务的背景是什么？为什么会做这个任务？"

### 4. 工作内容和目标
"具体要做哪些工作？目标是什么？"

用户提供描述后，先做规范化处理（参考下方"需求描述规范化规则"），展示后让用户确认。

### 5. 任务产出
根据已确认的需求描述，自动生成建议的产出清单。

生成规则：
- 每项产出包含"描述"和"预估天数"
- 参考历史相似任务的产出粒度
- 天数使用小数格式（1.0、0.5、2.5）
- 格式：`描述(N天)`

展示后询问用户是否调整。

**参与度自动计算**：所有产出天数之和。校验逻辑由服务端执行，AI 不需要自行计算。

### 6. 起止时间
"任务的开始日期是哪天？截止日期默认是月底，你可以修改。"

## 需求描述规范化规则

1. **结构化重组**：按"背景 → 目标 → 工作范围"三段式
2. **补充缺失**：用常识补充明显背景信息，但不编造用户没说的重要细节
3. **修正模糊**：把模糊表述变得具体可执行
   - ❌ "优化性能" → ✅ "将页面首屏加载时间从 3s 降低到 1.5s"
4. **控制长度**：最终规范化版本 ≤ 200 字
5. **保留确认**：展示后询问用户"是否准确？"

## 汇总展示

收集完所有信息后，用表格汇总：

| 字段 | 值 |
|------|-----|
| 标题 | xxx |
| 工时类型 | xxx |
| 需求描述 | xxx |
| 任务产出 | xxx |
| 参与度 | x.x 人天 |
| 开始日期 | xxxx-xx-xx |
| 截止日期 | xxxx-xx-xx |

询问用户："以上信息是否正确？确认后我将写入草稿文件。"

## 写入草稿

用户确认后，调用 `save_task_draft` Tool（MCP 模式）或写入 `draft.json` 文件（ttyd 模式）。

写入后告诉用户："草稿已保存，请在右侧面板查看并确认。"
```

### 4.4 prompts/tb_analyze.md

**来源**：`skills/task-analysis/SKILL.md`（原封不动迁移）

原文件内容迁移，不修改。占位符 `{task_context}`、`{kb_context}` 等保留。

---

## 5. 代码改动清单

### 5.1 需要改的文件

| 文件 | 改动 |
|------|------|
| `tbcreate/workspace.py` | `_claude_md_template()` 改为 `ai/prompts/tb_create.md` 文件读取；`init_workspace()` 更新路径 |
| `tbcreate/context.py` | 删除硬编码 CLAUDE.md（约 30 行），改用 workspace.py 的统一入口 |
| `knowledge/workspace.py` | 保留独立 `_claude_md_template()`（知识库场景不同） |
| `task_analysis/analysis.py` | 第 18 行路径从 `skills/task-analysis/SKILL.md` 改为 `prompts/tb_analyze.md` |
| `knowledge/dashboard_analysis.py` | 第 22 行路径从 `runtime/shared/.../SKILL.md` 改为 `ai/prompts/tb_analyze.md` |
| `task_analysis/routes.py` | 删除第 25 行 keyword-extract 引用（废弃功能） |
| `terminal/launcher.sh` | skills 目录 symlink 源从 `runtime/shared/.claude/skills/` 改为 `ai/prompts/` |

### 5.2 需要删除的文件

```
ai/rules/data_contracts.md          # 过时 API 文档
ai/rules/task_ticket.md             # 内容已迁移
ai/skills/tbcreate/SKILL.md         # 内容已迁移
ai/skills/task-analysis/SKILL.md    # 内容已迁移
ai/skills/task-analysis/tb_rule.md  # 内容已迁移
ai/skills/keyword-extract/SKILL.md  # 废弃
runtime/shared/.claude/skills/      # 改为从 ai/prompts/ 同步
```

### 5.3 需要新增的文件

```
ai/domain/work_hour.md              # 工时分类知识
ai/domain/task_spec.md              # TB 单字段规范
ai/prompts/tb_create.md             # 创建指令
ai/prompts/tb_analyze.md            # 分析 prompt（从旧文件迁移）
ai/scripts/install_prompts.sh       # 同步脚本
```

### 5.4 install_prompts.sh

```bash
#!/bin/bash
# 将 ai/prompts/ 安装到 runtime/shared/.claude/skills/
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROMPTS_DIR="$(cd "${SCRIPT_DIR}/../prompts" && pwd)"
RUNTIME_DIR="$(cd "${SCRIPT_DIR}/../runtime/shared/.claude/skills" && pwd)"

mkdir -p "${RUNTIME_DIR}"

# 清空旧内容
rm -rf "${RUNTIME_DIR:?}"/*

# 为每个 prompt 创建 skill 目录结构
for prompt_file in "${PROMPTS_DIR}"/*.md; do
    name="$(basename "${prompt_file}" .md)"
    skill_dir="${RUNTIME_DIR}/${name}"
    mkdir -p "${skill_dir}"
    cp "${prompt_file}" "${skill_dir}/SKILL.md"
    echo "[install] ${name} → ${skill_dir}/SKILL.md"
done

echo "Done. Installed $(ls "${PROMPTS_DIR}"/*.md | wc -l) prompts."
```

---

## 6. 迁移步骤

### Step 1：创建新目录和新文件（不影响运行）

```bash
mkdir -p ai/domain ai/prompts ai/scripts
# 按 4.1-4.4 的内容创建 4 个 .md 文件
```

### Step 2：更新代码引用

按 5.1 的清单逐个改。每改一个跑一次对应的功能确认无回归。

改动的代码量预估：

| 文件 | 改动行数 | 难度 |
|------|---------|------|
| `workspace.py` | ~40 行删，~15 行加 | 中 |
| `context.py` | ~30 行删 | 低 |
| `analysis.py` | 1 行（路径字符串） | 低 |
| `dashboard_analysis.py` | 1 行（路径字符串） | 低 |
| `routes.py` | ~5 行删 | 低 |
| `launcher.sh` | 1 行（路径字符串） | 低 |

### Step 3：用 install_prompts.sh 替换手动镜像

```bash
bash ai/scripts/install_prompts.sh
```

验证：`runtime/shared/.claude/skills/` 下的内容应与 `ai/prompts/` 完全一致。

### Step 4：删除旧文件

确认所有功能正常后删除 5.2 列出的文件。

### Step 5：更新 design doc

MCP 设计文档 `08-mcp-server-design.md` 中的 Resource/Prompt 路径引用改为指向新目录。

---

## 7. 对 MCP 设计的受益

清理后，MCP Server 的实现更干净：

```python
# ai/mcp/server.py

# Resources 直接读 domain/ → 领域知识
@mcp.resource("domain://tb/work-hour")
def get_work_hour_rules() -> str:
    return (Path(__file__).parent.parent / "domain" / "work_hour.md").read_text()

@mcp.resource("domain://tb/task-spec")
def get_task_spec() -> str:
    return (Path(__file__).parent.parent / "domain" / "task_spec.md").read_text()

# Prompts 直接读 prompts/ → AI 指令
@mcp.prompt()
def tb_create(user_name: str = "用户") -> str:
    template = (Path(__file__).parent.parent / "prompts" / "tb_create.md").read_text()
    return template.replace("{user_name}", user_name)
```

**一个知识点只存一处。** domain/ 是 Resources 的来源，prompts/ 是 Prompts 的来源。不再有镜像、不再有硬编码、不再有"改一处忘三处"。

---

## 8. 一句话总结

**domain/ 存事实，prompts/ 存指令，docs/ 存设计。删 rules/、删 skills/、删镜像目录、删硬编码字符串。一个知识点只在一个文件中。**
