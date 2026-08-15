# program_issue 数据库设计说明

本文描述“问题处理”项目同步数据的持久化与 customField 解析设计，重点覆盖：

- `program_issue`：任务列表快照（A 表）
- `program_issue_detail`：任务详情快照及解析字段（B 表）

本文是重新设计的基线文档。当前先记录已确认事实，字段拆分方案由后续逐项讨论确定。

---

## 1. 数据来源

| 项目 | 当前值 |
|---|---|
| 数据库 | `benti_management` |
| A 表 | `program_issue` |
| B 表 | `program_issue_detail` |
| 任务类型 | 问题处理 |
| 详情查询身份 | `query_user_id`，当前通常等于执行人 ID |
| 原始数据 | `custom_fields_json` / `raw_json` |

`program_issue_detail` 当前以 `(task_id, query_user_id)` 唯一，采用最新数据覆盖模式。

---

## 2. 设计原则

1. 原始 `customFields` 必须保留，拆列字段不能替代原始数据。
2. 每个业务 customField 单独定义解析规则，不能仅按“级联字段第 1/2/3 级”推断业务含义。
3. 同一任务中的不同级联字段互不混淆。例如“项目分类”和“车型”是两套不同的级联字段。
4. 空值应落为 `NULL`，不把缺失值伪造成“未填写”；报表展示层再决定是否显示“未填写”。
5. 字段命名优先表达业务含义；只有在确实表示同一字段路径时，才使用 `_level_1/_level_2/_level_3`。

---

## 3. 当前 B 表已存在的解析字段

| 当前列 | 当前含义 | 当前来源/问题 |
|---|---|---|
| `project_catagory_1` | 项目分类第 1 级 | 目标字段；来源 `665ee4b45b46f34b3e045af2` |
| `project_catagory_2` | 项目分类第 2 级 | 目标字段；替代旧的 `vehicle_type_2` |
| `project_catagory_3` | 项目分类第 3 级 | 目标字段；替代旧的 `project_name_3` |
| `vehicle_1` | 车型第 1 级 | 目标字段；来源 `668e05afbe23298626d61027` |
| `vehicle_2` | 车型第 2 级 | 目标字段；来源 `668e05afbe23298626d61027` |
| `problem_type_1` | 问题类型第 1 级 | 目标字段；来源 `67c56f477ed2b4b7bbd0cd69` |
| `problem_type_2` | 问题类型第 2 级 | 目标字段；来源 `67c56f477ed2b4b7bbd0cd69` |
| `problem_note_info_1` | 问题提示信息第 1 级 | 目标字段；来源 `67c572129590cd29ac9c5137` |
| `problem_note_info_2` | 问题提示信息第 2 级 | 目标字段；来源 `67c572129590cd29ac9c5137` |
| `problem_note_info_3` | 问题提示信息第 3 级 | 目标字段；来源 `67c572129590cd29ac9c5137` |
| `cause_level_1..3` | 问题原因层级 | 原因字段集合，当前同步代码支持多个 ID |
| `software_version` | JZTOTAL/软件版本 | `65a7be8938685843bf1c7d83` |

### 3.1 已确认的错误或不足

当前的 `vehicle_type_2` 并不是样例中的车型“EMMA标车”；它实际承载的是项目分类级联字段的第 2 级。

样例 `program_issue_detail.id = 7962` 中：

```text
项目分类字段：订单项目 / AMR / B+项目*
车型字段：EMMA标车 / EMMA K系列（举升、旋转举升）
```

当前代码只解析了前者：

```text
project_catagory_1 = 订单项目
project_catagory_2 = AMR
project_catagory_3 = B+项目*
```

后者尚未拆列，因此需要新增或重新命名车型相关字段。

目标拆分为：

```text
vehicle_1 = EMMA标车
vehicle_2 = EMMA K系列（举升、旋转举升）
```

---

## 4. 已确认的 customField

以下 ID 已从样例和现有同步代码确认：

| customField ID | 类型 | 业务含义 | 样例 |
|---|---|---|---|
| `665ee4b45b46f34b3e045af2` | cascading | 项目分类路径 | `订单项目 / AMR / B+项目*` |
| `668e05afbe23298626d61027` | cascading | 车型路径 | `EMMA标车 / EMMA K系列（举升、旋转举升）` |
| `67c56f477ed2b4b7bbd0cd69` | cascading | 问题类型 | `本体导航 / 导航` |
| `67c571aa5aed540b545e208c` 等 | cascading | 问题原因 | `外部因素 / 部署实施异常 / block动作部署` |
| `67c572129590cd29ac9c5137` | cascading | 问题提示信息 | `本体对接 / 对接 / 36021|There are problems with the perceived data` |
| `65a7be8938685843bf1c7d83` | dropDown | 软件版本 | `2.2403` |
| `624e4bf0972b3d03d3008c4c` | text | 问题描述 | 任务描述文本 |

> 注意：`668e05af...` 是根据当前样例确认的车型字段 ID。需要继续抽样确认 Q2 全部任务是否始终使用该 ID，还是存在历史/模板变体。

---

## 5. 当前解析链路

```text
钉钉任务详情
  └─ customFields
      ├─ _extract_cascading_project_fields()
      ├─ _extract_program_issue_label_levels()
      └─ _extract_program_issue_software_version()
          ↓
      _sync_one_detail_to_b_and_c()
          ↓
      program_issue_detail
```

当前相关实现：

| 文件 | 作用 |
|---|---|
| `backend/base/sync/task_sync.py` | customField 解析及 B 表写入 |
| `backend/base/db/orm.py` | `ProgramIssue` / `ProgramIssueDetail` 模型 |
| `backend/base/db/engine.py` | 缺列时自动补列 |
| `backend/scripts/backfill_program_issue_label_levels.py` | 回填问题类型、原因、软件版本 |
| `backend/base/scripts/backfill_b2_cascading.py` | 回填项目分类级联字段 |
| `diagnosis-agent/source-docs/onsite-top/scripts/program_issue_report.py` | Q2 报表读取 B 表字段 |

---

## 6. 待讨论的字段设计

以下问题按业务含义逐项确认，确认后再改模型、迁移、同步和回填：

### 6.1 项目分类

当前样例支持：

```text
project_catagory_1 = 订单项目
project_catagory_2 = AMR
project_catagory_3 = B+项目*
```

旧字段映射为：

| 旧字段 | 新字段 |
|---|---|
| `project_category_1` | `project_catagory_1` |
| `vehicle_type_2` | `project_catagory_2` |
| `project_name_3` | `project_catagory_3` |

目标字段统一使用 `project_catagory_1/2/3`。其中 `catagory` 为本次确定的字段拼写，后续代码和数据库设计均按此名称执行。

### 6.2 车型

已确定拆成：

```text
vehicle_1 = EMMA标车
vehicle_2 = EMMA K系列（举升、旋转举升）
```

当前车型级联字段只有两级，暂无 `vehicle_3`。

### 6.3 问题类型、问题原因、提示信息

问题类型只保存拆分后的两级字段，不额外保存完整路径，也不设计第三级字段。例如：

```text
problem_type_1 = 本体导航
problem_type_2 = 导航
```

问题提示信息固定拆分为三级。例如：

```text
problem_note_info_1 = 本体对接
problem_note_info_2 = 对接
problem_note_info_3 = 36021|There are problems with the perceived data
```

目前问题类型、问题原因、问题提示信息已按各自 customField 拆分，但还需要确认：

- 是否所有历史原因字段都统一折叠为 `cause_level_1..3`；
- 提示信息是否需要落独立列，而不是仅在 `raw_json` 中读取；
- 多选值是否需要 JSON 保存，而不是用 `; ` 拼接；
- 级联路径中的 ` / ` 是否始终代表层级分隔符。

---

## 7. 变更实施顺序

1. 抽样确认 customField ID 和实际路径结构。
2. 确认最终字段命名及旧字段兼容策略。
3. 修改 ORM 模型和自动迁移。
4. 修改同步解析及所有写入路径。
5. 编写/更新历史数据回填脚本。
6. 修改 `program_issue` 报表读取字段。
7. 用样例记录和 Q2 全量数据做新旧结果对比。

---

## 8. 变更记录

| 日期 | 内容 |
|---|---|
| 2026-08-12 | 新建设计文档；确认项目分类与车型是两套不同级联字段，样例 id=7962 的车型尚未拆列 |
