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
