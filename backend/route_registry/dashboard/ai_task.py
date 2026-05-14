"""Dashboard AI task ticket route.

Route:
  POST /ai-task-ticket  - Create a Teambition task from an AI-generated draft
"""

from flask import request

from route_registry.dashboard import _fail, _ok, _require_login, dashboard_bp


@dashboard_bp.route("/ai-task-ticket", methods=["POST"])
def ai_task_ticket():
    """Create a real Teambition task from a confirmed AI task draft.

    This is the dashboard compatibility endpoint. The primary route is
    POST /api/bt/ai/create_mission in ai.mission.routes.
    """
    from ai.mission.service import ai_create_mission_service

    user = _require_login()
    if not user:
        return _fail("unauthenticated", code=401, data={})

    payload = request.get_json(silent=True) or {}
    user_id = str((user or {}).get("user_id") or (user or {}).get("userid") or "").strip()
    if user_id:
        payload.setdefault("userId", user_id)
        payload.setdefault("executorId", user_id)

    result = ai_create_mission_service(payload)
    if not result.get("success"):
        status_code = int(((result.get("data") or {}).get("status_code")) or 400)
        return _fail(result.get("error", "create mission failed"), code=status_code, data=result)

    data = result.get("data") or {}
    task_id = str(data.get("taskId") or "")
    return _ok({
        "success": True,
        "taskId": task_id,
        "taskUrl": str(data.get("taskUrl") or ""),
        "message": "已创建任务单{}".format("：{}".format(task_id) if task_id else ""),
        "requestPayload": data.get("requestPayload") or {},
        "raw": data.get("dingtalk") or {},
    })
