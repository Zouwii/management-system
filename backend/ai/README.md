# AI 最小目录

当前目录只保留 Claude 子进程启动能力，不再提供独立 token API。

## 使用方式

在 `backend` 目录下执行：

```bash
python3 ai/start_claude_jz.py
```

该脚本会读取 `ai/config.json` 中的 `api_key/base_url/model`，并以 `claude --bare` 方式启动。

## AI 页面接入 ttyd

后端已提供签名会话接口：

- `POST /api/bt/ai/ttyd/session`

返回字段：

- `embedUrl`: 前端可直接用于 `iframe` 的地址（已附带 `ownerKey/model`）
- `port`: 当前 owner 对应 ttyd 端口

### 必配环境变量

- `AI_TTYD_BASE_URL`：ttyd 对外地址模板，默认 `http://127.0.0.1:{port}/`（支持 `{port}` 占位）
- `AI_TTYD_PORT_BASE`：ttyd 端口起始值，默认 `8800`
- `AI_TTYD_PORT_SPAN`：端口范围，默认 `400`

可选：

- `AI_TTYD_TOKEN_TTL_SECONDS`：保留字段（当前实现未使用）

### Nginx 反代建议（示意）

```nginx
location /ai/ttyd/ {
    proxy_pass http://127.0.0.1:7681/;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
}
```

生产建议在反代层做鉴权，并将 `AI_TTYD_BASE_URL` 配置为反代后的 HTTPS 地址。

