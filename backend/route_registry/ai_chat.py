"""AI 对话接口（先提供多轮测试入口）。"""

from flask import request

from services.ai_chat_service import (
    end_session_service,
    get_ai_models_service,
    run_multi_turn_chat_service,
    run_single_task_service,
    send_session_message_service,
)


def register(bp, ok, fail):
    @bp.route("/ai/models", methods=["GET"])
    def ai_models():
        try:
            timeout_seconds = int(request.args.get("timeoutSeconds") or request.args.get("timeout") or 15)
            out = get_ai_models_service(timeout_seconds=timeout_seconds)
            if out.get("success"):
                return ok(out)
            return fail(out.get("error", "fetch ai models failed"), code=400, data=out)
        except Exception as e:
            return fail(str(e), code=500, data={})

    @bp.route("/ai/chat/session_message", methods=["POST"])
    def ai_chat_session_message():
        try:
            payload = request.get_json(silent=True) or {}
            conversation_id = payload.get("conversationId") or payload.get("conversation_id") or ""
            prompt = payload.get("prompt") or payload.get("content") or ""
            model = str(payload.get("model") or "glm").strip() or "glm"
            timeout_seconds = int(payload.get("timeoutSeconds") or payload.get("timeout") or 45)
            out = send_session_message_service(
                conversation_id=conversation_id,
                prompt=prompt,
                model=model,
                timeout_seconds=timeout_seconds,
            )
            if out.get("success"):
                return ok(out)
            return fail(out.get("error", "ai session_message failed"), code=400, data=out)
        except Exception as e:
            return fail(str(e), code=500, data={})

    @bp.route("/ai/chat/session_end", methods=["POST"])
    def ai_chat_session_end():
        try:
            payload = request.get_json(silent=True) or {}
            conversation_id = payload.get("conversationId") or payload.get("conversation_id") or ""
            timeout_seconds = int(payload.get("timeoutSeconds") or payload.get("timeout") or 10)
            out = end_session_service(conversation_id=conversation_id, timeout_seconds=timeout_seconds)
            if out.get("success"):
                return ok(out)
            return fail(out.get("error", "ai session_end failed"), code=400, data=out)
        except Exception as e:
            return fail(str(e), code=500, data={})

    @bp.route("/ai/chat/single_task", methods=["POST"])
    def ai_chat_single_task():
        try:
            payload = request.get_json(silent=True) or {}
            prompt = payload.get("prompt") or ""
            model = str(payload.get("model") or "glm").strip() or "glm"
            timeout_ms = int(payload.get("timeoutMs") or payload.get("timeout_ms") or 120000)
            allowed_tools = payload.get("allowed_tools")
            out = run_single_task_service(
                prompt=prompt,
                model=model,
                timeout_ms=timeout_ms,
                allowed_tools=allowed_tools if isinstance(allowed_tools, list) else None,
            )
            if out.get("success"):
                return ok(out)
            return fail(out.get("error", "ai single_task failed"), code=400, data=out)
        except Exception as e:
            return fail(str(e), code=500, data={})

    @bp.route("/ai/chat/multi_turn", methods=["POST"])
    def ai_chat_multi_turn():
        try:
            payload = request.get_json(silent=True) or {}
            prompts = payload.get("prompts") or []
            model = str(payload.get("model") or "glm").strip() or "glm"
            timeout_seconds = int(payload.get("timeoutSeconds") or payload.get("timeout") or 30)
            out = run_multi_turn_chat_service(prompts=prompts, model=model, timeout_seconds=timeout_seconds)
            if out.get("success"):
                return ok(out)
            return fail(out.get("error", "ai multi_turn failed"), code=400, data=out)
        except Exception as e:
            return fail(str(e), code=500, data={})
