# Markdown 链路整治

> 状态：已完成 | 更新：2026-08-05

## 1. 问题

磁盘上 55GB markdown 文件的目录结构和 `kb_nodes.breadcrumb` 不匹配，导致 v3 `import` 步骤 0% 命中。

**根因：** breadcrumb 用 `workspace_id` 开头（如 `1oam4Sk7BMLXxn8K / 1. 工作规划 / ...`），磁盘用中文名开头（如 `本体开发部 / 1. 工作规划 / ...`）。`kb_workspaces.json` 已有完整映射。

**修复：** `_build_md_path()` 查 workspace_id → 中文名替换，加文件名 fallback 搜索。命中率 0% → **65%**。

### 数字

```
磁盘: 5185 个 .md 文件, 55GB
  本体开发部:          2242 文件,  9.1G
  产品专项知识库:       708 文件, 18G
  研发共享文档:        1057 文件,  5.3G
  订单专项知识库:       597 文件,  4.8G
  研发专项知识库:       332 文件, 11G
  研发体系全员文档库:   237 文件,  3.2G
  研发体系文档:         224 文件,  3.2G
  订单项目信息门户:      29 文件, 142M

DB: 6722 篇 kb_documents
  4057 篇 success (有 content, 可搜索)
  2598 篇 pending → ~1688 篇磁盘有文件(65%), ~910 篇需 MCP 下载
```

### 匹配现状（修复后）

| 策略 | 命中率 | 说明 |
|------|--------|------|
| breadcrumb + ws_name 映射 | **65%** | ✅ 已修复 |
| 文件名 fallback | 兜底 | ✅ 已加 |

## 2. 链路修复（已完成）

### 2.1 `_build_md_path()` — ✅ 已修复

- 查 `kb_workspaces.json` 把 `workspace_id` 替换为中文目录名
- breadcrumb 末尾文档名已去掉
- 路径不存在时 `rglob` 搜索同名文件作为 fallback

### 2.2 download 步骤 — ✅ `parent_dir` 参数

`/v3/download` 和 `/v3/import` 都支持 `parent_dir` 覆盖根目录。

## 3. 待办

### 3.1 MCP 下载 ~910 篇（外部依赖）

磁盘确实没有文件，需要 DingTalk MCP 下载。确认 MCP 可访问后跑 `/v3/download`。

### 3.2 全量 index（P1）

import 完成后跑 `/v3/index` 切块+embed。

### 3.3 旧 import_cleaned_markdown.py 退役（P3）

v3 import 稳定后废弃。

### 3.4 磁盘整理（可选）

磁盘文件路径现在和 `_build_md_path()` 一致（workspace_name 开头）。新下载的文件自动对齐。旧文件暂不需要迁移。

## 4. 状态

| 步骤 | 状态 | 说明 |
|------|------|------|
| breadcrumb 末尾去重 | ✅ 已修复 | `_build_md_path()` |
| `parent_dir` 参数 | ✅ 已加 | download/import/sync 都支持 |
| import fallback 搜索 | ✅ 已实现 | 文件名 fallback 搜索，命中率 0% → 65% |
| 批量 import pending | ✅ 已完成 | 增量导入 +57 新建 +413 更新 |
| 全量 index | ✅ 已完成 | 32915 leaf + 9169 parent → 31310 vectors |
| 磁盘整理脚本 | ❌ 待做 | 统一目录结构 |
| MCP 下载 | ❌ 待做 | 服务未运行 |
| 旧脚本退役 | ❌ 待做 | 等 v3 稳定 |
