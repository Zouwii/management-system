# 同步功能临时禁用记录

> 日期: 2026-06-09
> 原因: 钉钉 API 调用量过高，暂时禁用所有同步功能
> 预期解禁: **2026-06-23**（两周后）

---

## 一、禁用内容

| # | 功能 | 触发方式 | 禁用效果 |
|---|------|---------|---------|
| 1 | 知识库同步（小/大） | daemon 周一/四 04:00 + HTTP 手动 | 直接返回 error，不调用钉钉 |
| 2 | TB 任务全量同步 | daemon 每天 03:00 | 检测到标记文件即跳过 |
| 3 | 个人工时数据刷新 | 前端 "刷新" 按钮 | 返回 503 提示 |

---

## 二、实现机制

**标记文件：** `backend/runtime/sync_disabled`

```bash
# 当前状态：已禁用
touch backend/runtime/sync_disabled

# 两周后解禁：
rm backend/runtime/sync_disabled
```

3 个检查点，文件存在即拦截：

| 检查点 | 文件 | 代码 |
|--------|------|------|
| `sync_all_and_embed()` | `ai/knowledge/auto_sync.py:220` | `if _is_sync_disabled(): return {"ok": False, ...}` |
| `_auto_full_update_loop` | `base/app.py:160` | `if flag.exists(): print(SKIP); continue` |
| `personal_hours_update()` | `workhour/personal/routes.py:371` | `if flag.exists(): return 503` |

---

## 三、禁用期间仍可正常使用的功能

以下功能**不调用钉钉 API**，不受影响：

- ✅ 任务分析（`/task-analysis/*`）
- ✅ AI 知识库聊天（`/knowledge/chat`）
- ✅ 技术标书创建（`/tbcreate/*`）
- ✅ TTYD 终端（`/ttyd/*`）
- ✅ 绩效查询（`/stats/*`）
- ✅ Dashboard 工时看板（`/personal-hours`）
- ✅ MCP 工具（搜索知识库、分析任务等）
- ✅ 用户登录（`/auth/dingtalk/url`）

---

## 四、本次一并提交的改动

| 文件 | 改动内容 | 目的 |
|------|---------|------|
| `ai/knowledge/routes.py` | 3 处 `[sync-error]` 日志 | 同步失败时打印 nodeId/title/status |
| `ai/knowledge/auto_sync.py` | per-workspace 统计 → `print()` | daemon.log 可见每个知识库的 synced/failed/skipped |
| `ai/knowledge/auto_sync.py` | 打印前 5 个错误详情 | 快速定位失败原因 |
| `base/app.py` | `fcntl.flock` 文件锁 | 防止 Flask debug reloader 导致多进程重复同步 |
| `base/app.py` | TB 任务同步 disabled 检查 | 禁用期间不调钉钉 |
| `ai/knowledge/auto_sync.py` | `sync_all_and_embed` disabled 检查 | 禁用期间不调钉钉 |
| `workhour/personal/routes.py` | `personal_hours_update` disabled 检查 | 禁用期间不调钉钉 |

---

## 五、解禁步骤（2026-06-23）

```bash
# 1. 删除标记文件
rm backend/runtime/sync_disabled

# 2. 重启 daemon
bash run_on_pc_daemon.sh restart

# 3. 观察 daemon.log，确认首次同步正常
tail -f backend/runtime/tb_tool_bt_daemon.log
# 预期看到:
# [auto_sync] workspace=xxx synced=... changed=... failed=... skippedWb=...
# [sync-error] list_nodes failed ...  (如有失败会显示详情)
```

---

## 六、同步恢复后的关注点

解禁后第一次同步，关注以下日志：

1. **`[auto_sync] workspace=...`** — 每个知识库的成功/失败/跳过统计
2. **`[sync-error] ...`** — 具体哪些节点失败、什么状态码
3. **daemon 是否只启动一个** — 确认 `fcntl` 文件锁生效，日志中不应出现两个并发同步
4. **`[auto_knowledge_sync_loop] SKIP`** — 如果出现说明另一个进程已持锁，属于正常行为

如果解禁后 API 调用量仍然过高，可考虑：
- 降低 daemon 同步频率（当前每周 2 次 → 每周 1 次）
- 添加失败节点黑名单缓存
- 实现增量同步（基于 modifiedTime）
