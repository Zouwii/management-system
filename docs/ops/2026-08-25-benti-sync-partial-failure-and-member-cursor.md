# 团队增量同步单成员失败问题与后续改造计划

> 记录日期：2026-08-25  
> 涉及接口：`POST /api/bt/increase_sync`  
> 当前状态：问题已定位，失败日志已上线；部分成功与成员独立游标尚未实现

## 1. 问题背景

管理系统页面的“同步”按钮触发团队增量同步。当前实现会依次查询本体团队 20 名成员的钉钉任务列表，所有成员列表和任务详情都成功后，才统一写库并推进全局 `last_update_time`。

2026-08-25 下午，按钮多次返回 HTTP 500。最初的访问日志只记录了 `/api/bt/increase_sync` 返回 500，无法确认失败成员和钉钉响应内容。

本问题与 KB 同步无关：

- 同步按钮调用 `POST /api/bt/increase_sync`；
- 该接口只执行 TB 团队任务同步；
- `DINGTALK_KB_MCP_URL` 仅影响 KB 下载/同步及组合式定时任务中的 KB 阶段。

## 2. 已确认的故障证据

增加日志并部署后，再次触发同步，定位到以下失败：

| 字段 | 内容 |
|---|---|
| 成员 | 谢宇迪 |
| `user_id` | `246760621135238117` |
| 成员序号 | 12 / 20 |
| `project_id` | `647854bc4a622b2e3199fa5a` |
| 增量起点 | `2026-08-25T04:09:13.000Z`（北京时间 12:09:13） |
| 钉钉 HTTP 状态 | 500 |
| 钉钉错误码 | `unknownError` |
| 钉钉错误信息 | `未知错误` |
| 重试次数 | 3 次，全部失败 |
| 最后一次请求 ID | `01A0386F-5F71-7A1F-A150-4C4FE1635991` |

对应日志格式：

```text
[benti_sync] member_list_failed {
  "member_id": "246760621135238117",
  "member_index": 12,
  "member_count": 20,
  "project_id": "647854bc4a622b2e3199fa5a",
  "updated_gte": "2026-08-25T04:09:13.000Z",
  "attempt": 3,
  "max_attempts": 3,
  "status_code": 500,
  "code": "unknownError",
  "message": "未知错误",
  "request_id": "01A0386F-5F71-7A1F-A150-4C4FE1635991"
}
```

已排除：

- KB MCP URL 缺失；
- 本地同步锁冲突；
- `daily_sync_enabled` 限额开关关闭；
- 全局 token 获取失败；
- `project_id` 缺失；
- 本地数据库连接失败。

同批次前 11 名成员能够使用相同 token、项目和增量窗口成功请求，因此当前证据更倾向于成员数据或钉钉服务端针对该成员/查询条件的异常。

## 3. 当前实现的问题

当前团队同步位于 `backend/base/sync/task_sync.py` 的 `benti_team_incremental_update_service()`。

简化流程如下：

```text
读取全局 last_update_time
  → 遍历 20 名成员拉任务列表
    → 任意成员失败：立即 return 500
  → 合并并去重任务
  → 拉取任务详情
  → 写入 A/B/C/Issue 表
  → 推进全局 last_update_time
```

该设计带来几个问题：

1. 一名成员失败会阻断其他成员。
2. 失败前已经完成的钉钉 API 调用无法形成有效同步结果，浪费 API 配额。
3. 接口只能返回整体成功或整体失败，无法表达“19 人成功、1 人待重试”。
4. 全局游标无法区分每个成员的同步进度。
5. 如果部分失败时仍推进全局游标，会永久跳过失败成员在该时间窗口内的数据；因此当前代码只能选择整体不推进。

## 4. 已完成的临时处理

2026-08-25 已完成并部署以下日志增强：

- 每次成员列表重试失败时记录：
  - `member_id`、成员序号和总人数；
  - `project_id`；
  - 增量窗口；
  - 当前重试次数；
  - HTTP 状态、钉钉 `code/message/requestId`；
  - 分页数、已获取任务数和 token 刷新状态。
- 最终 500 响应中返回相同的失败上下文。
- 日志不记录 access token、AppSecret 或其他敏感凭据。
- 已增加对应回归测试。

该改动只增强可观测性，没有改变同步和写库语义。

### 4.1 临时恢复措施

为先恢复团队同步可用性，2026-08-25 临时将失败成员谢宇迪移出同步数据范围，并清理执行人为他的本地任务数据：

| 数据 | 删除行数 |
|---|---:|
| `user_character` | 1 |
| `project_tasks` | 14 |
| `project_task_details` | 14 |
| `sync_failures` | 4 |
| `project_task_overdue_details` | 0 |
| `program_issue` / `program_issue_detail` | 0 |
| `member_attendance` | 0 |

删除前已将匹配数据备份到服务器 MySQL 数据库：

```text
benti_management_backup_20260825_184115
```

处置完成后的状态：

- 团队同步成员数由 20 人变为 19 人；
- `benti_lock` 已释放；
- 5002 服务正常监听；
- 失败成员及其任务数据可以从备份库恢复；
- 该操作仅为临时绕过，不能替代部分成功和成员独立游标改造。

## 5. 短期改造：允许部分成功

短期可以先不引入成员游标表，按以下方式降低单点阻塞：

1. 成员列表请求连续三次失败后，不再立即返回。
2. 将失败信息写入现有 `sync_failures` 表：
   - `sync_type=benti_team_incremental`；
   - `phase=member_list`；
   - 写入 `project_id`、`executor_id`、错误信息、请求 ID 和增量窗口。
3. 把成员加入 `failedMembers`，继续处理其他成员。
4. 成功成员的任务正常拉详情并 upsert。
5. 只要存在失败成员，全局 `last_update_time` 就不推进。
6. 接口返回部分成功，而不是 HTTP 500。

建议返回：

```json
{
  "success": true,
  "partial": true,
  "memberCount": 20,
  "syncedMembers": 19,
  "failedMembers": [
    {
      "userId": "246760621135238117",
      "name": "谢宇迪",
      "code": "unknownError",
      "message": "未知错误",
      "requestId": "01A0386F-5F71-7A1F-A150-4C4FE1635991"
    }
  ],
  "cursorAdvanced": false
}
```

前端应提示：

```text
同步部分完成：19 人成功，谢宇迪失败，已记录待重试。
```

该方案数据安全，但下一次同步仍会从旧的全局游标重新查询所有成员，增加 API 调用量。

## 6. 中期改造：每成员独立游标

### 6.1 建议数据模型

不建议在 `config` 表中创建动态的 `last_update_time:<user_id>`。建议新增专用表：

```text
member_sync_cursors
├── id
├── sync_type
├── project_id
├── executor_id
├── cursor_at
├── last_attempt_at
├── last_success_at
├── status
├── error_code
├── error_message
├── request_id
├── created_at
└── updated_at
```

唯一键：

```text
(sync_type, project_id, executor_id)
```

游标至少要区分同步类型和项目，不能只按人员区分，否则不同项目或 DEV/Issue 链路会相互推进时间。

### 6.2 正确的游标推进方式

每次同步开始时先固定 `window_end`：

```text
window_start = member.cursor_at - overlap
window_end   = 本次同步开始时间
```

查询窗口：

```text
updated >= window_start
updated <  window_end
```

建议保留 2～5 分钟重叠窗口，依赖数据库 upsert 去重，以应对钉钉数据延迟和时钟误差。

不能把游标推进到“同步完成时间”。如果某任务在列表查询结束后、同步完成前发生更新，推进到完成时间会让该任务在下一轮被跳过。

### 6.3 成员成功与失败

- 成员列表、任务详情和数据库提交全部成功：将该成员游标推进到 `window_end`。
- 成员列表失败：游标不动，记录失败并继续其他成员。
- 成员任务详情失败：短期建议该成员游标不动；后续可增加任务详情重试队列。
- 下次同步可以只重试 `status=failed` 的成员。

本次问题在成员游标模式下应表现为：

```text
谢宇迪：游标仍为 2026-08-25 12:09:13
其他 19 人：游标推进到本次 window_end
```

### 6.4 任务转交与删除

需要额外验证以下边界：

- 任务从成员 A 转交给成员 B 时，钉钉是否会将该任务作为 B 的更新任务返回；
- 成员被移出项目或离职后，列表接口的行为；
- 任务删除、归档或取消执行者时是否存在可消费的 tombstone；
- 同一任务出现在多个成员列表时，跨成员 task ID 去重是否保持正确。

成员游标不会自动解决“任务从列表中消失但没有删除事件”的问题，该场景仍需要周期性校准或低频全量核对。

## 7. 全局 `last_update_time` 的现有职责

当前 `last_update_time` 不只是团队同步游标，还被多个模块复用：

| 职责 | 当前使用位置 |
|---|---|
| 四条增量同步链路的 TQL 起点 | `base/sync/task_sync.py` |
| 团队同步成功后推进时间 | `benti_team_incremental_update_service()` |
| 普通 DEV/Issue 和时间范围同步推进时间 | `base/sync/task_sync.py` |
| 页面展示“上次更新时间” | Dashboard、个人工时、团队统计、部门概览 |
| 自动计算防止同日重复触发 | `base/app.py` |
| 手动 touch 接口 | `base/config/service.py`、前端 Dashboard |
| 全量同步保存、重置和失败回滚 | `scripts/run_benti_full_update.py` |

因此不能直接删除或改成单个人的时间。

建议逐步拆分为：

```text
last_sync_attempt_at     最近一次同步尝试
last_partial_sync_at     最近一次部分成功
last_full_success_at     最近一次全团队成功
last_auto_calc_at        最近一次自动计算
member_sync_cursors      每成员真实增量游标
```

兼容阶段可以保留 `last_update_time`，将其定义为“最近一次全团队成功时间”，继续供旧页面和旧接口读取。

## 8. 迁移计划

### P0：问题可观测性（已完成）

- [x] 日志记录失败成员、钉钉错误码和请求 ID。
- [x] 500 响应返回失败上下文。
- [x] 部署并通过真实同步复现。

### P1：部分成功

- [ ] 成员列表失败后继续其他成员。
- [ ] 写入 `sync_failures.phase=member_list`。
- [ ] 返回 `partial/failedMembers/cursorAdvanced`。
- [ ] 前端展示部分成功及失败成员。
- [ ] 部分失败时保持全局游标不变。

### P2：成员独立游标

- [ ] 新增 `member_sync_cursors` 表及唯一键。
- [ ] 使用当前全局 `last_update_time` 初始化 20 名成员游标。
- [ ] 固定每次运行的 `window_end`。
- [ ] 增加 2～5 分钟重叠窗口。
- [ ] 成功成员独立推进，失败成员保持原游标。
- [ ] 支持只重试失败成员。

### P3：拆分全局时间语义

- [ ] 页面区分“最后尝试”“部分成功”“全部成功”。
- [ ] 自动计算改用 `last_auto_calc_at`。
- [ ] 普通 DEV、Issue、时间范围同步使用独立 sync type 游标。
- [ ] 清理前端直接调用 `touch_last_update_time` 的路径。

## 9. 验收标准

1. 单个成员钉钉接口连续返回 500 时，其他成员仍完成同步。
2. 返回结果能明确显示成功和失败成员。
3. 失败成员游标不推进，成功成员游标正确推进。
4. 重试失败成员成功后，不遗漏原失败窗口内的数据。
5. 同步期间产生的新任务不会因完成时间推进而丢失。
6. 不重复写入任务，A/B/C/Issue 表保持 upsert 幂等。
7. API 调用量、失败率和游标状态可通过日志或接口查询。
8. 现有 Dashboard 的“上次更新时间”在兼容期内保持可用。

## 10. 待确认问题

- 钉钉 `unknownError` 是否只由谢宇迪的成员/任务数据触发；
- 去掉 `updated` 条件或减小 `maxResults` 后是否仍返回 500；
- 是否需要向钉钉侧提交请求 ID 排查服务端日志；
- 成员被移出项目时游标记录如何归档；
- 详情失败采用“成员整体重试”还是“任务级重试队列”。
