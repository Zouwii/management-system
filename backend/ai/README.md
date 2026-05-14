# AI 模块使用说明

当前后端 AI 采用**功能模块化**组织，每个子功能独立一个目录。

## 目录结构

```
ai/
├── __init__.py              # 包入口，导出 register_all_routes()
├── config.json              # one-api 网关配置 (api_key / base_url / model)
├── README.md                # 本文件
│
├── task_assistant/          # 【功能1】AI 任务助手：对话→草稿
│   ├── routes.py            #   HTTP 路由 (conversations CRUD / messages / draft)
│   ├── service.py           #   对话管理与草稿合并
│   └── context.py           #   DB 任务上下文读取与 Markdown 生成
│
├── mission/                 # 【功能2】AI 任务创建：草稿→钉钉任务单
│   ├── routes.py            #   HTTP 路由 (create_mission / payload)
│   └── service.py           #   钉钉 API 调用与 payload 构建
│
├── terminal/                # 【功能3】AI 交互终端：ttyd + Claude CLI
│   ├── routes.py            #   HTTP 路由 (models / ttyd/session)
│   ├── session.py           #   ttyd 进程生命周期管理
│   └── launcher.sh          #   模型选择菜单 + claude 启动脚本
│
├── rules/                   # 【共享】AI 行为规则（供 LLM prompt 使用）
│   ├── task_ticket.md       #   任务单创建规则
│   ├── task_analysis.md     #   任务分析规则
│   └── data_contracts.md    #   数据契约定义
│
└── docs/                    # 【共享】AI 设计文档
    ├── execution_scheme.md  #   当前执行方案说明
    └── multi_user_design.md #   多用户架构设计
```

## 快速定位

| 你要做什么 | 去哪个文件 |
|-----------|-----------|
| 改 AI 任务助手的对话逻辑 | `ai/task_assistant/service.py` |
| 改 AI 任务助手的 HTTP 接口 | `ai/task_assistant/routes.py` |
| 改任务草稿如何保存/读取 | `ai/task_assistant/service.py` → `_save_json` / `_load_json` |
| 改任务上下文如何从 DB 读取 | `ai/task_assistant/context.py` |
| 改钉钉任务单创建逻辑 | `ai/mission/service.py` |
| 改钉钉任务单 HTTP 接口 | `ai/mission/routes.py` |
| 改 ttyd 终端会话管理 | `ai/terminal/session.py` |
| 改 ttyd 终端 HTTP 接口 | `ai/terminal/routes.py` |
| 改模型选择菜单 | `ai/terminal/launcher.sh` |
| 改 AI 行为规则/prompt | `ai/rules/*.md` |
| 改网关配置/模型 | `ai/config.json` |

## 推荐调用链路

### 任务助手对话
```
前端 Chat UI → POST /api/bt/ai/task-assistant/conversations
            → POST /api/bt/ai/task-assistant/conversations/<id>/messages
            → POST /api/bt/ai/task-assistant/conversations/<id>/draft/confirm
```

### 终端接入
```
前端 iframe → POST /api/bt/ai/ttyd/session → 获取 embedUrl → 嵌入页面
```

### 任务创建
```
前端确认草稿 → POST /api/bt/ai/create_mission → 钉钉 API → Teambition 任务单
             → POST /api/dashboard/ai-task-ticket （dashboard 兼容入口）
```

## 多用户隔离规则

- 以 `ownerKey` 作为会话隔离键
- 每个 `ownerKey` 对应一个活跃 ttyd 会话（进程 + 端口）
- 相同 `ownerKey` 重入优先复用会话，不同 `ownerKey` 互相隔离

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

## 常见问题

- `ttyd command not found in PATH` — 确认机器已安装 `ttyd`
- `claude command not found in PATH` — 确认 `claude` 已安装并在 PATH 中
- 页面黑屏或反复重连 — 检查 `AI_TTYD_BASE_URL`、端口占用、防火墙与反向代理
