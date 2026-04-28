#!/usr/bin/env python3
"""
AI 对话缓存管理脚本
位置: ai/cache/cache_manager.py
"""
import json
import os
import uuid
from datetime import datetime
from pathlib import Path

CACHE_DIR = Path(__file__).parent
CONVERSATIONS_DIR = CACHE_DIR / "conversations"
METADATA_FILE = CACHE_DIR / "metadata.json"
USER_INFO_FILE = CACHE_DIR / "user_info.json"

CONVERSATIONS_DIR.mkdir(exist_ok=True)


def get_current_conversation_id():
    """获取当前会话ID"""
    if METADATA_FILE.exists():
        meta = json.loads(METADATA_FILE.read_text())
        return meta.get("current_conversation_id")
    return None


def create_new_conversation():
    """创建新对话"""
    conv_id = str(uuid.uuid4())[:8]
    conv = {
        "conversation_id": conv_id,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "messages": [],
        "metadata": {}
    }
    (CONVERSATIONS_DIR / f"{conv_id}.json").write_text(json.dumps(conv, ensure_ascii=False, indent=2))

    meta = {"current_conversation_id": conv_id, "last_updated": datetime.now().isoformat()}
    METADATA_FILE.write_text(json.dumps(meta, ensure_ascii=False, indent=2))

    return conv_id


def save_message(role: str, content: str):
    """保存一条消息"""
    conv_id = get_current_conversation_id()
    if not conv_id:
        conv_id = create_new_conversation()

    conv_file = CONVERSATIONS_DIR / f"{conv_id}.json"
    conv = json.loads(conv_file.read_text())

    conv["messages"].append({
        "role": role,
        "content": content,
        "timestamp": datetime.now().isoformat()
    })
    conv["updated_at"] = datetime.now().isoformat()

    conv_file.write_text(json.dumps(conv, ensure_ascii=False, indent=2))

    # 更新 metadata
    meta = {"current_conversation_id": conv_id, "last_updated": datetime.now().isoformat()}
    METADATA_FILE.write_text(json.dumps(meta, ensure_ascii=False, indent=2))


def list_conversations():
    """列出所有对话"""
    if not CONVERSATIONS_DIR.exists():
        return []
    return sorted([f.stem for f in CONVERSATIONS_DIR.glob("*.json")])


def load_conversation(conv_id: str = None):
    """加载对话"""
    if not conv_id:
        conv_id = get_current_conversation_id()
    if not conv_id:
        return None

    conv_file = CONVERSATIONS_DIR / f"{conv_id}.json"
    if not conv_file.exists():
        return None

    return json.loads(conv_file.read_text())


def resume_conversation(conv_id: str = None):
    """恢复指定对话（设为当前）"""
    if not conv_id:
        conv_id = get_current_conversation_id()
    if not conv_id:
        return None

    if not (CONVERSATIONS_DIR / f"{conv_id}.json").exists():
        return None

    meta = {"current_conversation_id": conv_id, "last_updated": datetime.now().isoformat()}
    METADATA_FILE.write_text(json.dumps(meta, ensure_ascii=False, indent=2))

    return conv_id


def save_user_info(info: dict):
    """保存用户信息（如钉钉授权）"""
    USER_INFO_FILE.write_text(json.dumps(info, ensure_ascii=False, indent=2))


def load_user_info():
    """加载用户信息"""
    if USER_INFO_FILE.exists():
        return json.loads(USER_INFO_FILE.read_text())
    return None


if __name__ == "__main__":
    import sys

    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"

    if cmd == "list":
        convs = list_conversations()
        print(f"对话列表 ({len(convs)}):")
        for c in convs:
            print(f"  - {c}")
    elif cmd == "status":
        current = get_current_conversation_id()
        user = load_user_info()
        print(f"当前会话: {current or '无'}")
        print(f"用户信息: {user or '无'}")
    elif cmd == "save-user":
        # 保存用户信息
        info = {"unionId": "S5IGvDIokQ0mFnGFz3n7OgiEiE", "nick": "邹宏睿"}
        save_user_info(info)
        print("已保存用户信息")
    elif cmd == "new":
        cid = create_new_conversation()
        print(f"创建新对话: {cid}")
    elif cmd == "resume" and len(sys.argv) > 2:
        cid = resume_conversation(sys.argv[2])
        print(f"已切换到对话: {cid}")
    elif cmd == "show" and len(sys.argv) > 2:
        conv = load_conversation(sys.argv[2])
        if conv:
            print(json.dumps(conv, ensure_ascii=False, indent=2))
        else:
            print(f"对话 {sys.argv[2]} 不存在")
    else:
        print("用法: cache_manager.py <list|status|save-user|new|resume <id>|show <id>>")
