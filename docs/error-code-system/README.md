# 错误码知识库建设记录

> 最后更新：2026-07-22

---

## 背景

原有 kb 同步存在两个缺陷：

1. **不存文件夹** — `kb_documents` 只存 `node_type='FILE'`，目录层级全靠 `parent_id` 外键指向钉钉侧 nodeId，库内无法解析文件夹名称
2. **不递归** — 同步只拉 FOLDER 的直接子文件，子文件夹及内容全部跳过

导致"研发共享文档 / 1.功能使用指南"和"2.现场问题排查指南"下的内容大量缺失。

---

## 数据库变更

### 新增表

| 表名 | 说明 |
|------|------|
| `errcode_documents` | 错误码知识库文档表，含级联路径 |
| `errcode_chunks` | 错误码切片表，待后续分词/向量化 |

### `errcode_documents` 与 `kb_documents` 差异

| 字段 | kb_documents | errcode_documents |
|------|-------------|-------------------|
| `breadcrumb` | ✅ 已加 | ✅ 填充中 |
| `error_code` | ❌ | ✅ 从标题自动提取 |
| `error_desc` | ❌ | ✅ 错误一句话描述 |
| `jstate_path` | ❌ | ✅ 预留，如 `error/webservice/navi_precision_abnormal` |
| `solution` | ❌ | ✅ 预留，解法正文 |
| `content` | TEXT (64KB) | MEDIUMTEXT (16MB) |

---

## 同步脚本

**位置**：`management-system/scripts/selective_sync.py`

**功能**：按需定向拉取钉钉知识库节点，递归填充 breadcrumb 级联路径，支持可选下载正文。

```bash
# 预览（不写库）
python selective_sync.py <ws_id> <folder_node_id> --recursive --dry-run

# 拉元数据（快）
python selective_sync.py <ws_id> <folder_node_id> --recursive

# 拉元数据 + 正文（慢，每个文件 1 次 API）
python selective_sync.py <ws_id> <folder_node_id> --recursive --with-content
```

**目标表**：默认 `errcode_documents`，可用 `--target kb` 切换到 `kb_documents`。

**错误码自动提取**：从标题正则匹配 `^\d{5,7}` 提取 `error_code` 和 `error_desc`。

---

## 已同步数据

| 节点 | 名称 | 文件 | 文件夹 | workspace |
|------|------|------|--------|-----------|
| `AY39...` | 1.功能使用指南 | 266 | 54 | `nb9XJV8Pky0yOXy` |
| `EGd6...` | 2.现场问题排查指南 | 550 | 106 | `nb9XJV8Pky0yOXy` |
| **合计** | | **816** | **160** | |

其中 166 条自动提取到了 `error_code`。

**级联路径示例**：

```
2.现场问题排查指南 / 基础方法 / 错误码系统 / 错误码关联问题排查文档 / 基线相关问题排查文档 / 603001 到达后续任务的执行位置，前置任务未完成，强制停障！.adoc
```

---

## 待办

- [ ] `--with-content` 全量拉正文（816 条，耗时较长）
- [ ] 正文解析后填充 `solution` 字段
- [ ] `errcode_chunks` 切片 + 向量化
- [ ] 原有 `kb_documents` 历史数据回填 breadcrumb
