"""工作日耗时统计（workday_costhour）独立业务模块。

按项目类型、车型、任务类型维度聚合工作日耗时，支持团队对比和明细下钻。
数据源：project_task_detail / project_task_overdue_detail / program_issue_detail 三张表。

口径说明：
  - 仅使用 DB.workday_costhour 原始字段直接求和，不做任何工时系数换算。
  - 与 personal/aggregate.py 的有效工时口径分离，本模块不应用岗位系数。
  - 单位：人/天（person-day），即 Teambition 填报的原始工作日数值。
"""
