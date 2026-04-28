# AI 当前执行方案说明

本文档描述 `management-system/backend` 当前 AI 终端链路的实际执行方式（以当前代码为准）。

## 1. 总体目标

- 前端在 AI 页面通过 `ttyd` 嵌入终端。
- 后端按 `ownerKey` 管理 ttyd 会话（进程和端口）。
- 启动脚本 `easy_start_claude_jz` 负责：
  - 统一 one-api 网关
  - 模型菜单选择（含二级型号）
  - 切换到用户工作区后启动 `claude`

---

## 2. 请求与进程链路

### 2.1 前端调用

- 接口：`POST /bt/ai/ttyd/session`
- 入参核心：`ownerKey`（可选 `model`）

### 2.2 后端调度（`route_registry/ai_debug.py`）

1. 解析 `ownerKey`（优先请求体，否则从登录会话中推断）
2. 计算 `owner_safe = sha256(ownerKey)[:24]`
3. 按 `ownerKey` 查 `_TTYD_SESSIONS`
   - 存活则复用
   - 不存在/退出则新建
4. 端口分配逻辑：
   - 优先 `ownerKey` 稳定映射
   - 端口占用则在配置范围内顺延
5. 拉起进程：
   - `ttyd -i 127.0.0.1 -p <port> bash backend/easy_start_claude_jz`
6. 返回：
   - `embedUrl`
   - `ownerKey`
   - `ownerSafe`
   - `workspaceDir`
   - `port/pid`

---

## 3. 启动脚本执行步骤（`easy_start_claude_jz`）

脚本当前执行顺序：

1. 固定网关与 key
   - `ANTHROPIC_BASE_URL=http://one-api.server22.jz`
   - `ANTHROPIC_API_KEY`（脚本内默认值）
   - `unset ANTHROPIC_AUTH_TOKEN`
2. 补齐 `PATH`（兼容 ttyd 非交互 shell）
3. 计算用户标识与目录：
   - `ownerKey -> safe_owner`
   - 工作区：`runtime/users/<safe_owner>/workspaces/default`
4. 显示模型菜单（一级）
   - `claude / kimi / minimax / step / mimo / glm / deepseek`
5. 选择子型号（二级，可选）
   - 例如 minimax 下选择 `MiniMax-M2.7` / `MiniMax-M2.7-highspeed`
6. 设置 `ANTHROPIC_MODEL`
7. 启动参数携带 `--model`
8. `cd` 到用户工作区并执行：
   - `exec claude --model <selected_model>`

---

## 4. 模型选择规则（当前）

- 菜单选择结果同时影响：
  - `ANTHROPIC_MODEL` 环境变量
  - `claude --model <selected_model>` 参数
- one-api 网关不随菜单切换，保持固定。

---

## 5. 用户隔离现状（当前版本）

### 已实现

- ttyd 会话按 `ownerKey` 隔离（进程/端口）
- 工作区按 `safe_owner` 隔离：
  - `runtime/users/<safe_owner>/workspaces/default`

### 未完全实现

- 目前脚本未强制切换 `HOME` 与 `CLAUDE_CONFIG_DIR` 到用户目录
- 即：Claude 的配置态（`.claude`）仍可能来自当前系统用户环境，存在“配置共享/串用”风险

---

## 6. 关键目录

- 启动脚本：`backend/easy_start_claude_jz`
- 路由调度：`backend/route_registry/ai_debug.py`
- 运行目录根：`backend/runtime/`
- 用户工作区：`backend/runtime/users/<safe_owner>/workspaces/default`
- 共享 skills：`backend/runtime/shared/.claude/skills`

---

## 7. 运行与自测（最小）

在 `backend` 目录执行：

```bash
bash easy_start_claude_jz
```

观察点：

1. 菜单是否正常显示并可选择
2. 选择后是否显示当前模型
3. 是否进入用户工作区
4. 后端接口返回的 `workspaceDir` 与实际目录是否一致

---

## 8. 已知问题与后续建议

已知问题（当前）：

- 某些场景下 Claude 仍可能回落到官方端点（受本地配置态优先级影响）

后续建议（下一步）：

1. 真正启用配置隔离：
   - `HOME=runtime/users/<safe_owner>`
   - `CLAUDE_CONFIG_DIR=runtime/users/<safe_owner>/.claude`
2. 增加启动前配置一致性检查（打印最终生效 provider/base/model）
3. 为隔离目录提供初始化模板，避免首次启动行为漂移

