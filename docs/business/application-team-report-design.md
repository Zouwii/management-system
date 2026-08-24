# 应用组问题分析后端设计

## 1. 业务边界

应用组问题分析是独立业务，不复用工作日耗时的查询、聚合或接口。主数据来自
`program_issue_detail`；现场单关联和排查文档价值来自独立的
`onsite_problem_details`；用户筛选来自 `user_character.team_id = '3'`。

## 2. 查询接口

### `GET /api/application-team/options`

用于初始化筛选器，不返回报表结果：

```json
{
  "members": [{"userId": "钉钉用户ID", "name": "姓名"}],
  "years": [2026],
  "quarters": [1, 2, 3, 4],
  "dimensions": {
    "problem_type_1": [],
    "cause_level_1": [],
    "problem_note_info_1": [],
    "project_catagory_1": [],
    "priority": [],
    "software_version": []
  }
}
```

`years`、`quarters` 和 `dimensions` 都由 SQL 实际已有记录生成，不在前端维护枚举。

### `POST /api/application-team/report`

请求体：

```json
{"year": 2026, "quarter": 2, "executorId": ""}
```

`executorId` 为空表示全部应用组用户；有值时必须属于应用组用户。问题类型统计固定只
使用 `program_issue_detail`，用户口径是 `executor_id`，时间口径是
`created_at_ding`，不使用 `need_statistic`。查询时间范围是季度左闭右开：
`[created_at_ding >= start, created_at_ding < end)`。

## 3. 最终结果表数量

页面按 **11 张结果表** 设计，其中 10 张统计表、1 张关联明细表：

| 序号 | key | 结果表 | 数据来源/行列 |
|---:|---|---|---|
| 1 | `typeStats` | 问题类型统计 | `problem_type_1/2`，单数、占比 |
| 2 | `causeStats.navigation` | 导航问题原因统计 | `cause_level_1/2/3` |
| 3 | `causeStats.localization` | 定位问题原因统计 | `cause_level_1/2/3` |
| 4 | `causeStats.mapping` | 建图问题原因统计 | `cause_level_1/2/3` |
| 5 | `promptStats.navigation` | 导航问题提示信息统计 | `problem_note_info_1/2/3` |
| 6 | `promptStats.localization` | 定位问题提示信息统计 | `problem_note_info_1/2/3` |
| 7 | `handlingStats` | 问题处理方式及耗时 | 当前源表尚未有结构化字段，暂不伪造结果 |
| 8 | `priorityMatrix` | 优先级矩阵 | SQL `priority` × 问题类型 |
| 9 | `documentValueMatrix` | 排查文档价值矩阵 | 现场单 `doc_value` × 问题类型 |
| 10 | `projectMatrix` | 项目 × 问题类型矩阵 | `project_catagory_1/2/3` × 问题类型 |
| 11 | `onsiteLinks` | 关联现场单子 | `task_id` 关联明细，包含关联数量和单号 |

接口响应中的 `resultTableCount` 固定为 11，`resultTables` 给出表名和类型，方便前端
按契约渲染。`details` 保留 SQL 明细下钻，不能替代上述统计表。

## 4. 尚未接入的字段

`handlingStats` 需要在 `program_issue_detail` 或关联现场单表中明确“问题处理方式”和
“耗时”的 customField 映射后再增加结构化 SQL 列，并补充同步解析和历史回填。在字段
确认前接口返回 `configured: false`，避免把工作日耗时误当成问题处理耗时。
