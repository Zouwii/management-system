"""AI 任务单创建路由。"""

from flask import request, session

from services.ai_mission_service import ai_create_mission_service, build_ai_mission_create_payload
from services.ai_task_assistant_service import (
    create_task_assistant_conversation,
    get_task_assistant_conversation,
    save_task_assistant_draft,
    send_task_assistant_message,
)


def _require_login():
    user = session.get("auth_user")
    if not user:
        return None
    return user


def register(bp, ok, fail):
    @bp.route("/ai/task-assistant/conversations", methods=["POST"])
    def ai_task_assistant_create_conversation():
        """创建当前用户的 AI 任务助手会话，并读取该用户任务上下文。"""
        user = _require_login()
        if not user:
            return fail("unauthenticated", code=401, data={})
        try:
            return ok(create_task_assistant_conversation(user))
        except Exception as e:
            return fail(str(e), code=500, data={})

    @bp.route("/ai/task-assistant/conversations/<conversation_id>", methods=["GET"])
    def ai_task_assistant_get_conversation(conversation_id):
        """读取当前用户自己的 AI 任务助手会话。"""
        user = _require_login()
        if not user:
            return fail("unauthenticated", code=401, data={})
        try:
            return ok(get_task_assistant_conversation(user, conversation_id))
        except FileNotFoundError as e:
            return fail(str(e), code=404, data={})
        except Exception as e:
            return fail(str(e), code=500, data={})

    @bp.route("/ai/task-assistant/conversations/<conversation_id>/messages", methods=["POST"])
    def ai_task_assistant_send_message(conversation_id):
        """接收用户描述，返回引导回复和结构化任务草稿。"""
        user = _require_login()
        if not user:
            return fail("unauthenticated", code=401, data={})
        try:
            payload = request.get_json(silent=True) or {}
            content = str(payload.get("content") or payload.get("message") or "").strip()
            return ok(send_task_assistant_message(user, conversation_id, content))
        except FileNotFoundError as e:
            return fail(str(e), code=404, data={})
        except ValueError as e:
            return fail(str(e), code=400, data={})
        except Exception as e:
            return fail(str(e), code=500, data={})

    @bp.route("/ai/task-assistant/conversations/<conversation_id>/draft/confirm", methods=["POST"])
    def ai_task_assistant_confirm_draft(conversation_id):
        """保存临时任务草稿文件；后续正式任务单接口可从这里接入。"""
        user = _require_login()
        if not user:
            return fail("unauthenticated", code=401, data={})
        try:
            payload = request.get_json(silent=True) or {}
            draft = payload.get("draft") if isinstance(payload.get("draft"), dict) else None
            return ok(save_task_assistant_draft(user, conversation_id, draft=draft))
        except FileNotFoundError as e:
            return fail(str(e), code=404, data={})
        except Exception as e:
            return fail(str(e), code=500, data={})

    @bp.route("/ai/create_mission/payload", methods=["POST"])
    def ai_create_mission_payload():
        """只生成钉钉 create payload，不真正创建任务，方便联调模板。"""
        try:
            payload = request.get_json(silent=True) or {}
            return ok({"requestPayload": build_ai_mission_create_payload(payload)})
        except Exception as e:
            return fail(str(e), code=400, data={})

    @bp.route("/ai/create_mission", methods=["POST"])
    def ai_create_mission():
        """按 AI 草稿创建 TB/钉钉任务单。"""
        try:
            payload = request.get_json(silent=True) or {}
            result = ai_create_mission_service(payload)
            if result.get("success"):
                return ok(result)
            status_code = ((result.get("data") or {}).get("status_code")) or 400
            return fail(result.get("error", "create mission failed"), code=int(status_code), data=result)
        except Exception as e:
            return fail(str(e), code=500, data={})
