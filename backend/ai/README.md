# AI 使用说明（ttyd-only）

当前后端 AI 只保留 **ttyd 终端模式**。旧 PTY 聊天链路已移除。

## 目录结构

- `config.json`：Claude 网关配置（`api_key` / `base_url` / `model`）
- `start_claude_jz.py`：本地直启 Claude 的入口脚本（调试用）
- `AI_MULTI_USER_DESIGN.md`：多用户架构设计文档

## 推荐调用链路（用户目录隔离）

1. 调用 `POST /bt/ai/ttyd/session` 创建或复用终端会话
2. 前端用返回的 `embedUrl` 通过 `iframe` 直连终端
3. 启动脚本按 `ownerKey` 自动切到用户专属目录并加载共享 skills

## 多用户隔离规则

- 以 `ownerKey` 作为会话隔离键
- 每个 `ownerKey` 对应一个活跃 ttyd 会话（进程 + 端口）
- 相同 `ownerKey` 重入优先复用会话，不同 `ownerKey` 互相隔离

## 接口

### 1) 创建/获取 ttyd 会话

- `POST /bt/ai/ttyd/session`

请求示例：

```json
{
  "ownerKey": "user-001",
  "model": "MiniMax-M2.7"
}
```

响应关键字段：

- `embedUrl`：前端 `iframe` 地址
- `ownerKey`：后端最终解析出的用户标识
- `ownerSafe`：用户安全目录名（sha256 截断）
- `userRoot`：用户根目录
- `workspaceDir`：用户工作区目录
- `model`：当前会话模型
- `port`：ttyd 监听端口
- `pid`：ttyd 进程号

## 配置项

### `ai/config.json`

```json
{
  "api_key": "sk-xxx",
  "base_url": "http://one-api.server22.jz",
  "model": "MiniMax-M2.7"
}
```

### 环境变量

- `AI_TTYD_BASE_URL`：ttyd 对外地址模板，默认 `http://127.0.0.1:{port}/`
- `AI_TTYD_PORT_BASE`：端口起始值，默认 `8800`
- `AI_TTYD_PORT_SPAN`：端口池跨度，默认 `400`

## 本地调试

在 `backend` 目录执行：

```bash
python3 ai/start_claude_jz.py
```

用途：

- 验证 `ai/config.json` 是否可用
- 验证当前环境能否找到 `claude` 命令
- 验证用户隔离目录是否创建在 `backend/runtime/users/*`

## skills 开发与发布

- 共享 skills 目录：`backend/runtime/shared/.claude/skills`
- 每个用户会话启动时会把共享 skills 合并到：
  - `backend/runtime/users/<ownerSafe>/.claude/skills`
- 你本地调试完 skill 后，发布时只需同步共享 skills 目录到服务器同路径

## 常见问题

- `ttyd command not found in PATH`
  - 确认机器已安装 `ttyd`，且服务启动环境 `PATH` 可见
- ``claude` command not found in PATH`
  - 确认 `claude` 已安装，并在后端进程继承的 `PATH` 中
- 页面黑屏或反复重连
  - 优先检查 `AI_TTYD_BASE_URL`、端口占用、防火墙与反向代理配置

