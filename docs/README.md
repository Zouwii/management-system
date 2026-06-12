# 项目文档索引

## 🏗 架构

| 文档 | 说明 |
|------|------|
| [ARCHITECTURE.md](architecture/ARCHITECTURE.md) | 后端架构：目录结构、模块职责、daemon 线程、请求链路 |
| [../CLAUDE.md](../CLAUDE.md) | 项目总览：技术栈、开发命令、部署、钉钉 API 监控、同步禁用 |

## 📊 数据库

| 文档 | 说明 |
|------|------|
| [database-design.md](database/database-design.md) | MySQL 主库：A/B/C 表、sync_runs、user_character、api_call_logs |
| [performance-database-design.md](database/performance-database-design.md) | 绩效库：nav/servo 季度绩效表、计算规则 |

## 🤖 AI

| 文档 | 说明 |
|------|------|
| [ai-development-analysis.md](ai/ai-development-analysis.md) | AI 开发全流程：知识库、任务分析、Teambition 创建、MCP |
| [ai-tbcreate-design.md](ai/ai-tbcreate-design.md) | Teambition 任务创建设计 |
| [MCP_使用说明.md](ai/MCP_使用说明.md) | MCP Server 使用说明：连接方式、Tools、Resources |

## 📋 业务

| 文档 | 说明 |
|------|------|
| [workday-costhour-design.md](business/workday-costhour-design.md) | 工时与工天换算：workday_costhour 计算逻辑 |
| [季度绩效计算说明.md](business/季度绩效计算说明.md) | 季度绩效考核：评分维度、计算公式 |

## 🔧 运维

| 文档 | 说明 |
|------|------|
| [server-connection.md](ops/server-connection.md) | 服务器连接：SSH、日志、数据库查询、重启、同步控制 |
| [sync-disabled-record.md](ops/sync-disabled-record.md) | 同步禁用记录（已整合到 CLAUDE.md） |
