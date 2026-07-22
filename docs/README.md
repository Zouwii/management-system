# 项目文档索引

> 所有文档集中在 `docs/` 下，按模块分目录。后端代码中不再散落文档。

---

## 🔴 错误码系统（← 当前核心工作）

| 文档 | 说明 |
|------|------|
| [error-code-system/README.md](error-code-system/README.md) | 建设记录：数据库设计、同步脚本、待办 |
| [error-code-system/导航相关问题排查.md](error-code-system/导航相关问题排查.md) | 614-619 错误码总表 |

**脚本**：`scripts/selective_sync.py` — 定向递归同步钉钉知识库到 `errcode_documents`

---

## 🏗 架构

| 文档 | 说明 |
|------|------|
| [architecture/ARCHITECTURE.md](architecture/ARCHITECTURE.md) | 后端架构：目录结构、模块职责、daemon 线程、请求链路 |
| [architecture/sync-and-lock.md](architecture/sync-and-lock.md) | 同步锁机制设计 |

---

## 📊 数据库

| 文档 | 说明 |
|------|------|
| [database/database-design.md](database/database-design.md) | MySQL 主库：A/B/C 表、sync_runs、user_character、api_call_logs |
| [database/performance-database-design.md](database/performance-database-design.md) | 绩效库：nav/servo 季度绩效表、计算规则 |
| [database/onsite-problem-design.md](database/onsite-problem-design.md) | 现场问题模块设计 |

---

## 🤖 AI 模块

### 使用说明
| 文档 | 说明 |
|------|------|
| [ai/MCP_使用说明.md](ai/MCP_使用说明.md) | MCP Server 使用说明：连接方式、Tools、Resources |
| [ai/ai-development-analysis.md](ai/ai-development-analysis.md) | AI 开发全流程：知识库、任务分析、Teambition 创建、MCP |
| [ai/ai-tbcreate-design.md](ai/ai-tbcreate-design.md) | Teambition 任务创建设计 |
| [ai/dev-server-diff.md](ai/dev-server-diff.md) | 开发环境与服务器差异 |
| [ai/ai-module-readme.md](ai/ai-module-readme.md) | AI 模块总览 |

### 设计文档

**kb-rag** — 知识库 & RAG
| 文档 | 说明 |
|------|------|
| [ai/design/kb-rag/01-why-rag-over-skill.md](ai/design/kb-rag/01-why-rag-over-skill.md) | 为什么用 RAG 而非 Skill |
| [ai/design/kb-rag/04-knowledge-service-design.md](ai/design/kb-rag/04-knowledge-service-design.md) | 知识库服务设计 |
| [ai/design/kb-rag/05-kb-database-design.md](ai/design/kb-rag/05-kb-database-design.md) | 知识库数据库设计 |
| [ai/design/kb-rag/06-knowledge-base-rag.md](ai/design/kb-rag/06-knowledge-base-rag.md) | 知识库 RAG 方案 |
| [ai/design/kb-rag/13-rag-retrieval-benchmark.md](ai/design/kb-rag/13-rag-retrieval-benchmark.md) | RAG 检索基准 |
| [ai/design/kb-rag/14-rag-fidelity-experiment.md](ai/design/kb-rag/14-rag-fidelity-experiment.md) | RAG 保真度实验 |

**task** — 任务创建 & 分析
| 文档 | 说明 |
|------|------|
| [ai/design/task/07-ai-task-analysis-design.md](ai/design/task/07-ai-task-analysis-design.md) | 任务分析设计 |
| [ai/design/task/09-task-creation-paths.md](ai/design/task/09-task-creation-paths.md) | 任务创建路径 |

**mcp** — MCP Server
| 文档 | 说明 |
|------|------|
| [ai/design/mcp/08-mcp-server-design.md](ai/design/mcp/08-mcp-server-design.md) | MCP Server 设计 |

**architecture** — 架构 & 基础设施
| 文档 | 说明 |
|------|------|
| [ai/design/architecture/02-execution-scheme.md](ai/design/architecture/02-execution-scheme.md) | 执行方案 |
| [ai/design/architecture/03-multi-user-design.md](ai/design/architecture/03-multi-user-design.md) | 多用户设计 |
| [ai/design/architecture/11-ai-architecture.md](ai/design/architecture/11-ai-architecture.md) | AI 整体架构 |
| [ai/design/architecture/12-claude-config-layout.md](ai/design/architecture/12-claude-config-layout.md) | Claude 配置布局 |
| [ai/design/architecture/09-rules-skills-cleanup.md](ai/design/architecture/09-rules-skills-cleanup.md) | Rules/Skills 清理 |
| [ai/design/architecture/钉钉API调用分析.md](ai/design/architecture/钉钉API调用分析.md) | 钉钉 API 分析 |

### RAG 实验
| 文档 | 说明 |
|------|------|
| [ai/rag-experiments/01-RAG检索优化-调研与实验方案.md](ai/rag-experiments/01-RAG检索优化-调研与实验方案.md) | 检索优化调研 |
| [ai/rag-experiments/02-how-to-build-testset.md](ai/rag-experiments/02-how-to-build-testset.md) | 测试集构建 |
| [ai/rag-experiments/03-step1-annotation.md](ai/rag-experiments/03-step1-annotation.md) | 标注流程 |
| [ai/rag-experiments/04-10-RAG检索调研与优化方案.md](ai/rag-experiments/04-10-RAG检索调研与优化方案.md) | 检索优化方案 |
| [ai/rag-experiments/05-13-rag-retrieval-benchmark.md](ai/rag-experiments/05-13-rag-retrieval-benchmark.md) | 检索基准测试 |

### 领域规则
| 文档 | 说明 |
|------|------|
| [ai/domain/tb_rule.md](ai/domain/tb_rule.md) | Teambition 规则 |
| [ai/domain/work_hour.md](ai/domain/work_hour.md) | 工时规则 |

---

## 📋 业务

| 文档 | 说明 |
|------|------|
| [business/workday-costhour-design.md](business/workday-costhour-design.md) | 工时与工天换算：workday_costhour 计算逻辑 |
| [business/季度绩效计算说明.md](business/季度绩效计算说明.md) | 季度绩效考核：评分维度、计算公式 |

---

## 🔧 运维

| 文档 | 说明 |
|------|------|
| [ops/server-connection.md](ops/server-connection.md) | 服务器连接：SSH、日志、数据库查询、重启、同步控制 |
| [ops/sync-disabled-record.md](ops/sync-disabled-record.md) | 同步禁用记录 |

