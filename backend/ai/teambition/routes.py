"""Teambition task creation route.

POST /ai/create_teambition  - Create a Teambition task from an AI draft
"""

from flask import request, session

from ai.teambition.service import create_task


def register(bp, ok, fail):
    @bp.route("/ai/create_teambition", methods=["POST"])
    def ai_create_teambition():
        """Create a Teambition task from the confirmed AI task draft.

        Request body: { title, workType, requirementDesc, outputs,
                        dueDate, startDate, executorId?, userId? }
        """
        body = request.get_json(silent=True) or {}
        auth_user = session.get("auth_user") or {}

        if isinstance(auth_user, dict):
            user_id = str(
                auth_user.get("user_id") or auth_user.get("userid") or ""
            ).strip()
            if user_id:
                body.setdefault("userId", user_id)
                body.setdefault("executorId", user_id)

        result = create_task(body)
        if not result.get("success"):
            status_code = int(
                ((result.get("data") or {}).get("statusCode")) or 400
            )
            return fail(
                result.get("error", "create task failed"),
                code=status_code,
                data=result.get("data", {}),
            )

        data = result.get("data", {})
        return ok({
            "success": True,
            "taskId": data.get("taskId", ""),
            "taskUrl": data.get("taskUrl", ""),
            "message": "任务已创建",
            "requestPayload": data.get("requestPayload", {}),
        })
