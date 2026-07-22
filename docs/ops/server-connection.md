# Server Operations — 服务器运维操作

当用户说 "连接服务器" / "查看日志" / "查数据库" / "重启服务" 时使用。

## 服务器信息

| 项目 | 值 |
|------|-----|
| 主机 | 172.19.3.79 |
| 用户 | jz |
| 密码 | 1 |
| 应用路径 | /home/jz/zhr/tb_tool_bt/ |
| MySQL | mysql -u root -p123456 benti_management |
| 服务端口 | 5002 |
| API 前缀 | http://172.19.3.79:5002/api/bt |

## 连接方式

```bash
# 方式 1: sshpass (推荐，免交互)
sshpass -p '1' ssh -o StrictHostKeyChecking=no jz@172.19.3.79

# 方式 2: 手动输入密码
ssh jz@172.19.3.79
# 密码: 1
```

## 查看服务状态

```bash
sshpass -p '1' ssh jz@172.19.3.79 "ps aux | grep python"
```

## 实时日志

```bash
sshpass -p '1' ssh jz@172.19.3.79 "tail -f /home/jz/zhr/tb_tool_bt/backend/runtime/tb_tool_bt_daemon.log"
```

## 查询数据库

```bash
# 表列表
sshpass -p '1' ssh jz@172.19.3.79 "mysql -u root -p123456 tb_management -e 'SHOW TABLES;'"

# API 调用量
sshpass -p '1' ssh jz@172.19.3.79 "mysql -u root -p123456 tb_management -e 'SELECT COUNT(*) FROM api_call_logs;'"

# 按日统计
sshpass -p '1' ssh jz@172.19.3.79 "mysql -u root -p123456 tb_management -e \"
SELECT DATE(created_at) day, endpoint, source, COUNT(*) calls,
  SUM(CASE WHEN status>=400 THEN 1 ELSE 0 END) errors
FROM api_call_logs GROUP BY day, endpoint, source ORDER BY day DESC LIMIT 20;\""

# 最近 50 条调用
sshpass -p '1' ssh jz@172.19.3.79 "mysql -u root -p123456 tb_management -e 'SELECT endpoint,status,latency_ms,created_at FROM api_call_logs ORDER BY id DESC LIMIT 50;'"
```

## API 监控

```bash
# 当天统计
curl -s http://172.19.3.79:5002/api/bt/monitor/api-stats | python3 -m json.tool

# 指定日期
curl -s "http://172.19.3.79:5002/api/bt/monitor/api-stats?day=2026-06-11" | python3 -m json.tool
```

## 服务管理

```bash
# 重启
sshpass -p '1' ssh jz@172.19.3.79 "cd /home/jz/zhr/tb_tool_bt/backend && bash run_on_pc_daemon.sh restart"

# 查看当前 daemon 状态
sshpass -p '1' ssh jz@172.19.3.79 "cd /home/jz/zhr/tb_tool_bt/backend && bash run_on_pc_daemon.sh status"
```

## 同步控制

```bash
# 禁用同步
sshpass -p '1' ssh jz@172.19.3.79 "touch /home/jz/zhr/tb_tool_bt/backend/runtime/sync_disabled"

# 恢复同步
sshpass -p '1' ssh jz@172.19.3.79 "rm /home/jz/zhr/tb_tool_bt/backend/runtime/sync_disabled && cd /home/jz/zhr/tb_tool_bt/backend && bash run_on_pc_daemon.sh restart"

# 检查是否禁用
sshpass -p '1' ssh jz@172.19.3.79 "test -f /home/jz/zhr/tb_tool_bt/backend/runtime/sync_disabled && echo DISABLED || echo ENABLED"
```
# 离线模式 / 同步禁用说明

> 更新: 2026-06-12
> 当钉钉 API 不可用时，通过离线模式保证系统正常使用。

---

## 一、背景

系统依赖钉钉 API 完成 OAuth 登录和数据同步（Teambition 项目任务）。当钉钉 API 不可用（网络故障、限流、服务宕机）时：
- **登录**：无法通过钉钉 OAuth 进入系统
- **数据同步**：无法从 Teambition 拉取最新任务数据

离线模式解决这两个问题：用户通过本地账户登录，系统读取已有 DB 数据。

---

## 二、启用离线模式

### 2.1 创建同步禁用标记

```bash
touch backend/runtime/sync_disabled
```

该文件存在时，所有钉钉 API 同步入口被拦截。**不创建此文件则离线登录后仍可触发同步**。

### 2.2 用户登录

打开系统登录页 → 点击底部「**离线模式登录**」→ 下拉选择用户 → 输入密码（123456）→ 点击「本地登录」。

后端接口：
| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/bt/auth/local/users` | GET | 返回 user_character 表中可用用户列表（character != 2） |
| `/api/bt/auth/local/login` | POST | user_id + password → 验证 → 建立 session |

### 2.3 恢复钉钉登录

登录页点击「**← 返回钉钉登录**」即可切回 OAuth 登录。

---

## 三、同步拦截点（sync_disabled 检查）

标记文件 `backend/runtime/sync_disabled` 存在时，以下入口返回 503：

| 检查点 | 文件 | 入口 |
|--------|------|------|
| `_is_sync_disabled()` | `base/sync/routes.py` | `/time_range_update`、`/full_update`、`/db/sync/project-tasks`、`/db/sync/task-detail`、`/db/sync/task-details-batch` |
| `_is_sync_disabled()` | `base/projects/routes.py` | `/query_project_tasks` 的 `sync_ab_*` 路径 + 自动落库路径 |
| `full_update_service()` | `base/sync/task_sync.py` | 全量同步内部双重校验 |
| `_auto_full_update_loop` | `base/app.py` | daemon 每日 03:00 定时触发 |
| `_auto_knowledge_sync_loop` | `base/app.py` | daemon 知识库大小同步 |

---

## 四、离线模式可正常使用的功能

所有读 DB 的功能不受影响：

- ✅ 用户登录（离线模式）
- ✅ Dashboard 工时看板（个人/团队）
- ✅ 绩效考核查询与计算
- ✅ AI 任务分析（基于 DB 中已有数据）
- ✅ AI 知识库聊天（RAG 检索）
- ✅ TTYD 终端 / MCP 工具
- ✅ 用户/项目配置管理

---

## 五、恢复在线模式

```bash
# 1. 删除标记文件
rm backend/runtime/sync_disabled

# 2. 重启 daemon（如需恢复定时同步）
bash backend/run_on_pc_daemon.sh restart
```
