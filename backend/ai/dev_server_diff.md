# 本地开发机 vs 服务器（172.19.3.79）差异记录

## 文件状态（已同步 ✅）

| 文件 | 状态 | 说明 |
|------|------|------|
| `backend/ai/terminal/session.py` | ✅ 一致 | 均含 `-W`、`0.0.0.0` 绑定 |
| `backend/ai/terminal/launcher.sh` | ✅ 一致 | 均无硬编码 API key，始终显示模型选择菜单 |
| `backend/ai/config.json` | ✅ 一致 | 同一份 one-api gateway 配置 |
| `backend/app.py` | ✅ 一致 | — |
| `backend/ai/tbcreate/routes.py` | ✅ 一致 | — |
| `backend/ai/tbcreate/workspace.py` | ✅ 一致 | — |

## 存在差异

### 1. `.env` 文件

服务器多了 3 行（AI_TTYD_BASE_URL）：

```
# AI ttyd public base URL（让前端 iframe 连到服务器，而非 127.0.0.1）
AI_TTYD_BASE_URL=http://172.19.3.79:{port}/
```

**原因**：前端 iframe 从浏览器加载 ttyd（端口 9035），不能用 `127.0.0.1`（那是浏览器的本机，不是服务器）。

**本地不需要**：本地开发时前端也跑在 localhost，`127.0.0.1` 就是本机。

### 2. ttyd 版本

| 环境 | 版本 |
|------|------|
| 本地 | 1.6.3 |
| 服务器 | 1.7.4 |

两者都是旧版（最新为 3.x），基本功能一致。输入问题的关键是 `-W` 参数而非版本差异。

### 3. Node.js 版本

| 环境 | 版本 |
|------|------|
| 本地 | v20.20.2 |
| 服务器 | v18.19.1 |

Claude CLI 依赖 Node.js，两个版本都兼容。

### 4. 启动方式

| 环境 | 后端端口 | 启动命令 |
|------|---------|---------|
| 本地 | 5001（默认） | `python app.py` 或 `run_on_pc.sh` |
| 服务器 | 5002（FLASK_RUN_PORT） | `run_on_pc_daemon.sh` |

### 5. 运行时目录

| 环境 | workspace 路径 |
|------|---------------|
| 本地 | `backend/runtime/users/<safe_hash>/workspaces/default/` |
| 服务器 | 同左，但根路径为 `/home/jz/zhr/tb_tool_bt/` |

## 部署流程

```bash
# 构建 + 打包（在 one-key 目录执行）
bash package-tb-tool-bt.sh

# 部署到服务器
bash deploy-tb-tool-bt.sh
```

注意：`package-tb-tool-bt.sh` 会删除 `runtime/` 目录，部署后需重新初始化（访问 AI 页面时会自动创建）。
