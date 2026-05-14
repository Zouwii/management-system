"""HTTP routes for AI mission (Teambition task) creation.

Endpoints:
  POST /ai/create_mission/payload   - Build & return the DingTalk payload (debug)
  POST /ai/create_mission           - Actually create a Teambition task via DingTalk API
"""

from flask import request

from ai.mission.service import ai_create_mission_service, build_ai_mission_create_payload


def register(bp, ok, fail):
    """Register mission creation routes on the given Blueprint."""

    @bp.route("/ai/create_mission/payload", methods=["POST"])
    def ai_create_mission_payload():
        """Build a DingTalk create-task payload from an AI draft (no side effects).

        Useful for debugging the payload structure before creating real tasks.
        """
        try:
            payload = request.get_json(silent=True) or {}
            return ok({"requestPayload": build_ai_mission_create_payload(payload)})
        except Exception as e:
            return fail(str(e), code=400, data={})

    @bp.route("/ai/create_mission", methods=["POST"])
    def ai_create_mission():
        """Create a real Teambition task from an AI draft via the DingTalk API.

        Request body must include userId and the draft fields.
        """
        try:
            payload = request.get_json(silent=True) or {}
            result = ai_create_mission_service(payload)
            if result.get("success"):
                return ok(result)
            status_code = ((result.get("data") or {}).get("status_code")) or 400
            return fail(result.get("error", "create mission failed"), code=int(status_code), data=result)
        except Exception as e:
            return fail(str(e), code=500, data={})
