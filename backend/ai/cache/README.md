# AI 对话缓存

用于存储 AI 与用户的对话历史，支持跨会话恢复。

## 目录结构

```
cache/
├── conversations/    # 对话文件，每轮对话一个 JSON
├── metadata.json     # 元数据（当前会话ID、最后更新时间等）
└── user_info.json    # 用户授权信息（钉钉 unionId 等）
```

## 对话文件格式

```json
{
  "conversation_id": "uuid",
  "created_at": "2026-04-23T10:00:00",
  "updated_at": "2026-04-23T11:30:00",
  "messages": [
    {"role": "user", "content": "...", "timestamp": "..."},
    {"role": "assistant", "content": "...", "timestamp": "..."}
  ],
  "metadata": {
    "dingtalk_union_id": "xxx",
    "source": "ttyd|terminal"
  }
}
```

## 缓存管理

```bash
# 列出所有对话
ls cache/conversations/

# 查看元数据
cat cache/metadata.json

# 继续上次的对话
python3 cache_manager.py resume
```
