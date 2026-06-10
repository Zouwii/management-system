# AI 终端执行方案说明

本文档描述当前 AI 终端链路的实际执行方式。以代码为准：

- `backend/ai/terminal/routes.py`
- `backend/ai/terminal/session.py`
- `backend/ai/terminal/launcher.sh`

旧的 `easy_start_claude_jz` / `ai/start_claude_jz.py` 启动方式已废弃，ttyd 只走 `terminal/launcher.sh`。

---

## 1. 总体目标

- 前端在 AI 页面通过 iframe 嵌入 ttyd。
- 后端按 `ownerKey + purpose` 管理 ttyd 会话、端口和进程。
- Claude CLI 使用 `ai/config.json` 中的 one-api 网关配置。
- ttyd 会话最多存活 2 小时，超时自动回收。

---

## 2. 请求与进程链路

### 2.1 前端调用

- 接口：`POST /api/bt/ai/ttyd/session`
- 入参核心：
  - `ownerKey`：用户隔离键
  - `model`：可选；为空时使用 `ai/config.json` 的 `model`
  - `skill`：可选；作为 Claude 初始提示

### 2.2 后端调度

入口：`ai/terminal/routes.py::ai_ttyd_session`

1. 解析 `ownerKey`，优先请求体，否则从登录会话推断。
2. 读取 `ai/config.json`，确定 `api_key`、`base_url`、默认 `model`。
3. 调用 `ensure_ttyd_session()`。
4. 返回：
   - `embedUrl`
   - `ownerKey`
   - `ownerSafe`
   - `workspaceDir`
   - `model`
   - `skill`
   - `port`
   - `pid`
   - `createdAt`
   - `expiresAt`
   - `ttlSeconds`

### 2.3 子进程链路

```text
前端 iframe
  -> POST /api/bt/ai/ttyd/session
  -> ai/terminal/routes.py
  -> ai/terminal/session.py
  -> ttyd -W -i 0.0.0.0 -p <port> bash ai/terminal/launcher.sh [skill]
  -> claude --bare --model <model> <initial prompt>
```

---

## 3. 会话复用与重建

内存映射：`_TTYD_SESSIONS`

键：`ownerKey + purpose`

复用条件：

- 已有进程仍存活
- `model` 与本次请求一致
- `skill` 与本次请求一致
- 未超过 TTL

重建条件：

- 进程不存在或已退出
- 模型变化
- skill 变化
- TTL 过期

重建前会对旧 ttyd 进程组发送 `SIGTERM`，避免只杀 ttyd 而留下 Claude 子进程。

---

## 4. 端口分配

- 默认端口池：`8800 ~ 9199`
- 配置项：
  - `AI_TTYD_PORT_BASE`：默认 `8800`
  - `AI_TTYD_PORT_SPAN`：默认 `400`
- 首选端口由 `ownerKey + purpose` 稳定映射。
- 首选端口占用时，在端口池内顺延扫描。

---

## 5. 生命周期与回收

配置项：

- `AI_TTYD_TTL_SECONDS`：默认 `7200` 秒，最小 `60` 秒

实现：

1. 每次创建会话时写入 `created_at` 和 `expires_at`。
2. 每次请求前调用 `_cleanup_ttyd_sessions_locked()` 清理死亡或过期进程。
3. 后台 `ttyd-session-janitor` 线程定期扫描 `_TTYD_SESSIONS`。
4. 回收动作写入 `runtime/logs/ai_debug_subprocess.log`。

停止日志示例：

```json
{"phase":"ttyd_session_stop","reason":"ttl_expired","port":9154,"pid":12345}
```

常见 `reason`：

- `ttl_expired`
- `dead`
- `model_or_skill_changed`
- `stale`

---

## 6. 启动环境

`session.py::make_env()` 负责构造 ttyd 子进程环境：

- 注入：
  - `ANTHROPIC_API_KEY`
  - `ANTHROPIC_BASE_URL`
  - `ANTHROPIC_MODEL`
  - `AI_OWNER_KEY`
  - `AI_OWNER_NAME`
  - `AI_SAFE_OWNER`
  - `AI_FLASK_BASE_URL`
- 清理：
  - `OPENAI_API_KEY`
  - `OPENAI_API_BASE`
  - `OPENAI_BASE_URL`
  - `OPENAI_MODEL`
- 优先 PATH：
  - `~/.nvm/versions/node/v20.20.2/bin`
  - `~/.local/bin`

`launcher.sh` 内部也会再次清理 `OPENAI_*`，防止 shell 初始化文件污染 Claude CLI。

---

## 7. 用户工作区

路径：

```text
backend/runtime/users/<safe_owner>/workspaces/default
```

其中：

```text
safe_owner = sha256(ownerKey)[:24]
```

工作区由 `ai/tbcreate/workspace.py` 初始化，核心文件：

- `CLAUDE.md`
- `AI_TASK_CONTEXT.md`
- `TASK_TICKET_RULES.md`
- `draft.json`

---

## 8. 当前保留文件

ttyd 相关有效文件：

```text
backend/ai/terminal/routes.py
backend/ai/terminal/session.py
backend/ai/terminal/launcher.sh
backend/ai/tbcreate/workspace.py
```

已废弃并清理：

```text
backend/ai/start_claude_jz.py
backend/easy_start_claude_jz
```
