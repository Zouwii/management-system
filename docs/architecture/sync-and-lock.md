# 同步与锁设计

> 更新: 2026-07-22

---

## 1. 同步类型

| # | 名称 | 端点 | 触发 | 数据表 |
|---|------|------|------|--------|
| 1 | **团队增量同步** | `POST /api/bt/increase_sync` | 按钮 + daemon 周一 03:00 | `project_tasks`(A) + `project_task_details`(B) + `project_task_overdue_details`(C) + `program_issue` + `program_issue_detail` |
| 2 | **现场问题全量** | `POST /api/bt/onsite/sync` | 手动 | `onsite_problem_tasks`(A) + `onsite_problem_details`(B) |
| 3 | **本体清表全量** | 已关闭 | 手动 Python shell | 清表重拉全部 |

### 1.1 团队增量同步

遍历 `user_character` 全体用户，每人依次跑 DEV + Issue 增量：

```
钉钉 TQL: (updated >= last_update_time)
```

拉自上次同步以来被修改过的任务，写 A + B + C + Issue。

### 1.2 现场问题全量

拉 `projectId=616e6868a46ec51df166f4cd` 全量任务，写 A + B。详见 `docs/database/onsite-problem-design.md`。

### 1.3 本体清表全量

2026-07-16 关闭。DELETE 全部表 → 重置 `last_update_time` → 遍历全用户重拉。API 消耗极大，改手动执行。

---

## 2. 锁

### 2.1 锁 key 注册表

定义在 `base/sync/lock.py`：

| 常量 | key | 用途 |
|------|-----|------|
| `LOCK_BENTI` | `benti_lock` | 团队增量同步 |
| `LOCK_ONSITE` | `onsite_lock` | 现场问题全量 |

新增同步 → 在此文件加 `LOCK_XXX` 常量 → 调用 `sync_guard(LOCK_XXX, owner)`。

### 2.2 使用方式

```python
from base.sync.lock import sync_guard, SyncBlocked, LOCK_BENTI

try:
    with sync_guard(LOCK_BENTI, f"increase@{int(time.time())}"):
        do_sync()
except SyncBlocked as e:
    return fail(str(e), code=503)
```

`sync_guard` = `is_sync_enabled()` 检查 + `acquire_update_lock` + finally `release_update_lock`，TTL 30min。

### 2.3 各同步需要的锁

| 同步 | 分布式锁 |
|------|:--:|
| 团队增量同步 | ✅ `LOCK_BENTI` |
| 现场问题全量 | ✅ `LOCK_ONSITE` |
| 本体清表全量 | ✅ `LOCK_BENTI` |

---

## 3. 开关

唯一开关：

| 函数 | config key | 管理者 | 默认 | 作用 |
|------|-----------|--------|------|------|
| `is_sync_enabled()` | `daily_sync_enabled` | **api_monitor 自动** | true | API 超额 → 写 false → 全部同步停止；低于限额 → 写 true |

---

## 4. API 限额

### 4.1 机制

| 层级 | 位置 | 频率 |
|------|------|------|
| Route | `sync_guard` → `is_sync_enabled()` | 同步入口 |
| Service | `_do_request` → `check_api_allowed()` | 每次钉钉请求 |
| Service | `_record` → `record_api_call()` | 每次钉钉请求后写入 + 更新开关 |

### 4.2 限额规则

| | 每月 1 号 | 其他日期 |
|---|----------|----------|
| 硬限 | 15000 | 5000 |

### 4.3 监控

```
GET /api/bt/monitor/api-stats
→ { disabled, total_calls, total_errors, top_endpoints }
```

---

## 5. 相关文件

| 文件 | 内容 |
|------|------|
| `base/sync/lock.py` | `sync_guard` / `LOCK_BENTI` / `LOCK_ONSITE` / 锁操作 |
| `base/sync/task_sync.py` | `normal_incremental_update_service` / `sync_project_details_in_time_range_service` |
| `base/projects/task_service.py` | API 查询 + `check_api_allowed` |
| `base/projects/routes.py` | `increase_sync` 路由 |
| `base/config/service.py` | `is_sync_enabled()` |
| `base/api_monitor.py` | API 限额监控 + 自动开关 |
| `base/onsite_problem/` | 现场问题同步模块 |
| `base/app.py` | daemon 定时同步 |

---

## 6. 修订记录

| 日期 | 说明 |
|------|------|
| 2026-07-22 | 重构：3 种同步、2 个锁、1 个开关、1 层限额；删除 `is_full_sync_enabled`、`incremental_update` |
