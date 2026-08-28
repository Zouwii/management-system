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

### 设计文档

**RAG** — 知识库检索增强

| 文档 | 说明 |
|------|------|
| [ai/rag/RAG-设计.md](ai/rag/RAG-设计.md) | 系统设计：架构、DB、检索策略、API |
| [ai/rag/RAG-对照试验.md](ai/rag/RAG-对照试验.md) | 对照试验：检索基准、保真度、测试集 |
| [ai/rag/RAG-优化方案.md](ai/rag/RAG-优化方案.md) | 优化路线：Phase 1-3、模型选型、待办 |
| [ai/rag/RAG-v2-00-文档索引.md](ai/rag/RAG-v2-00-文档索引.md) | RAG v2 文档顺序、当前状态和下一步入口 |

**其他设计**
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
| [ai/design/architecture/03-multi-user-design.md](ai/design/architecture/03-multi-user-design.md) | 多用户设计 |
| [ai/design/architecture/11-ai-architecture.md](ai/design/architecture/11-ai-architecture.md) | AI 整体架构 |
| [ai/design/architecture/钉钉API调用分析.md](ai/design/architecture/钉钉API调用分析.md) | 钉钉 API 分析 |

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
| [ops/server-connection.md](ops/server-connection.md) | 服务器连接：SSH、日志、数据库、重启、同步控制、离线模式 |
| [ops/2026-08-25-benti-sync-partial-failure-and-member-cursor.md](ops/2026-08-25-benti-sync-partial-failure-and-member-cursor.md) | 团队同步单成员 500 问题记录、部分成功方案与成员独立游标改造计划 |
