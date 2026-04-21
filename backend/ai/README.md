# AI 最小目录

当前目录只保留 Claude 子进程启动能力，不再提供独立 token API。

## 使用方式

在 `backend` 目录下执行：

```bash
python3 ai/start_claude_jz.py
```

该脚本会读取 `ai/config.json` 中的 `api_key/base_url/model`，并以 `claude --bare` 方式启动。

