"""HTTP routes for AI tbcreate (Teambition create) task drafting.

Endpoints:
  POST /ai/tbcreate/workspace/init  - Initialize user workspace with context files
  GET  /ai/tbcreate/draft/current   - Read draft.json from the user's workspace
  POST /ai/tbcreate/draft/save      - Save/overwrite draft.json from frontend edits
"""

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict

from flask import request, session

from ai.tbcreate.workspace import init_workspace
from ai.terminal.session import resolve_owner_key, user_workspace


def _empty_draft() -> Dict[str, Any]:
    """Return a default empty task draft structure."""
    return {
        "title": "",
        "workType": "指派型",
        "requirementDesc": "",
        "outputs": [],
        "participationLevel": 1.0,
        "dueDate": "",
        "startDate": "",
    }


def _read_draft(owner_key: str) -> Dict[str, Any]:
    """Read draft.json from the user's workspace, return parsed dict or empty draft."""
    ws = user_workspace(owner_key)
    draft_path = os.path.join(ws["workspace_dir"], "draft.json")
    if os.path.isfile(draft_path):
        try:
            with open(draft_path, "r", encoding="utf-8") as f:
                draft = json.load(f)
            if isinstance(draft, dict):
                return draft
        except (json.JSONDecodeError, IOError):
            pass
    return _empty_draft()


def register(bp, ok, fail):
    """Register tbcreate routes on the given Blueprint."""

    @bp.route("/ai/tbcreate/workspace/init", methods=["POST"])
    def ai_tbcreate_workspace_init():
        """Initialize the user's AI workspace with context files.

        Writes CLAUDE.md, AI_TASK_CONTEXT.md, and TASK_TICKET_RULES.md
        into runtime/users/<ownerKey>/workspaces/default/.

        Request body (optional): {"ownerKey": "..."}
        Falls back to session auth_user.
        """
        payload = request.get_json(silent=True) or {}
        auth_user = session.get("auth_user") or {}
        owner_key = resolve_owner_key(
            payload if isinstance(payload, dict) else {}, auth_user
        )
        try:
            result = init_workspace(owner_key, auth_user if isinstance(auth_user, dict) else None)
            return ok(result)
        except Exception as e:
            return fail(str(e), code=500, data={})

    @bp.route("/ai/tbcreate/draft/current", methods=["GET"])
    def ai_tbcreate_draft_current():
        """Read the current draft.json from the user's workspace.

        Query params: ownerKey (optional, falls back to session auth_user).
        Returns the parsed draft JSON, or an empty draft if no file exists.
        """
        payload = request.args.to_dict() or {}
        auth_user = session.get("auth_user") or {}
        owner_key = resolve_owner_key(
            payload if isinstance(payload, dict) else {}, auth_user
        )
        return ok(_read_draft(owner_key))

    @bp.route("/ai/tbcreate/draft/save", methods=["POST"])
    def ai_tbcreate_draft_save():
        """Save/overwrite draft.json from frontend edits.

        When the user modifies fields in the right panel, the frontend
        calls this endpoint to persist changes back to draft.json,
        so Claude can read the updated draft on the next interaction.

        Request body: {"ownerKey": "...", "draft": {...}}
        """
        body = request.get_json(silent=True) or {}
        auth_user = session.get("auth_user") or {}
        owner_key = resolve_owner_key(
            body if isinstance(body, dict) else {}, auth_user
        )
        draft = body.get("draft") if isinstance(body, dict) else None
        if not isinstance(draft, dict):
            return fail("missing or invalid 'draft' field", code=400, data={})

        ws = user_workspace(owner_key)
        draft_dir = ws["workspace_dir"]
        os.makedirs(draft_dir, exist_ok=True)
        draft_path = os.path.join(draft_dir, "draft.json")
        try:
            with open(draft_path, "w", encoding="utf-8") as f:
                json.dump(draft, f, ensure_ascii=False, indent=2)
            return ok({
                "saved": True,
                "savedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            })
        except IOError as e:
            return fail(f"failed to write draft.json: {e}", code=500, data={})
