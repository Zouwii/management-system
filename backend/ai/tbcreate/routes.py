"""HTTP routes for AI tbcreate (Teambition create) task drafting.

Endpoints:
  POST /ai/tbcreate/workspace/init    - Initialize user workspace with context files
  GET  /ai/tbcreate/draft/current     - Read draft.json from the user's workspace
  POST /ai/tbcreate/draft/save        - Save/overwrite draft.json from frontend edits
  POST /ai/tbcreate/draft/notify      - Notify frontend that draft was updated (from Claude)
  GET  /ai/tbcreate/draft/events      - SSE stream: frontend listens for draft updates
  GET  /ai/tbcreate/tasks             - Query parent tasks eligible for selection
"""

import json
import os
import queue as queue_module
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List

from flask import request, session, Response, stream_with_context
from sqlalchemy import or_

from ai.tbcreate.workspace import init_workspace
from ai.terminal.session import resolve_owner_key, user_workspace
from base.db.engine import SessionLocal
from base.db.orm import ProjectTaskDetail

# SSE: owner_key -> list of queues (one per connected frontend)
_draft_sse_queues: Dict[str, List[queue_module.Queue]] = {}
_draft_sse_lock = threading.Lock()


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
        "parentTaskId": "",
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
        """Initialize the user's AI workspace with context files."""
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
        """Read the current draft.json from the user's workspace."""
        payload = request.args.to_dict() or {}
        auth_user = session.get("auth_user") or {}
        owner_key = resolve_owner_key(
            payload if isinstance(payload, dict) else {}, auth_user
        )
        return ok(_read_draft(owner_key))

    @bp.route("/ai/tbcreate/tasks", methods=["GET"])
    def ai_tbcreate_tasks():
        """Return tasks eligible as parent — tasks whose task_id appears as
        another task's parent_task_id in project_task_details.

        Steps:
          1. Collect distinct parent_task_id values.
          2. Look up those task_ids, return taskId + content.
          3. Skip rows with empty content.
        """
        auth_user = session.get("auth_user") or {}
        if not isinstance(auth_user, dict):
            return ok([])
        user_id = str(
            auth_user.get("user_id") or auth_user.get("userid") or ""
        ).strip()
        if not user_id:
            return ok([])

        db_session = SessionLocal()
        try:
            # Step 1: collect distinct parent_task_id / parent_id values.
            # (Some tasks only have parent_id populated, not parent_task_id.)
            parent_rows = (
                db_session.query(
                    ProjectTaskDetail.parent_task_id,
                    ProjectTaskDetail.parent_id,
                )
                .filter(
                    ProjectTaskDetail.query_user_id == user_id,
                    or_(
                        ProjectTaskDetail.parent_task_id.isnot(None),
                        ProjectTaskDetail.parent_id.isnot(None),
                    ),
                )
                .distinct()
                .all()
            )
            # Merge both columns; prefer parent_task_id, fall back to parent_id.
            parent_ids = set()
            for r in parent_rows:
                pid = (r.parent_task_id or r.parent_id or "").strip()
                if pid:
                    parent_ids.add(pid)
            parent_ids = sorted(parent_ids)
            if not parent_ids:
                return ok([])

            # Step 2: look up task content (skip query_user_id filter —
            # the same parent task may have been fetched by a different user).
            # Deduplicate by task_id since the table's unique key is
            # (task_id, query_user_id).
            detail_rows = (
                db_session.query(
                    ProjectTaskDetail.task_id,
                    ProjectTaskDetail.content,
                )
                .filter(ProjectTaskDetail.task_id.in_(parent_ids))
                .all()
            )
            seen = set()
            items = []
            for row in detail_rows:
                if row.task_id in seen:
                    continue
                seen.add(row.task_id)
                title = (row.content or "").strip()
                if title:
                    items.append({"taskId": row.task_id, "title": title})

            items.sort(key=lambda x: x["title"].lower())
            return ok(items)
        finally:
            db_session.close()

    @bp.route("/ai/tbcreate/draft/save", methods=["POST"])
    def ai_tbcreate_draft_save():
        """Save/overwrite draft.json from frontend edits."""
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
            # Touch flag file so Claude knows the draft was modified externally
            flag_path = os.path.join(draft_dir, "draft_changed.flag")
            with open(flag_path, "w") as _:
                pass
            return ok({
                "saved": True,
                "savedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            })
        except IOError as e:
            return fail(f"failed to write draft.json: {e}", code=500, data={})

    # ── SSE helpers ───────────────────────────────────────────

    def _sse_broadcast(owner_key: str, event: str, data: dict) -> None:
        """Push an SSE event to all connected frontends for this owner_key."""
        payload = json.dumps(data, ensure_ascii=False)
        with _draft_sse_lock:
            queues = _draft_sse_queues.get(owner_key, [])
            dead = []
            for q in queues:
                try:
                    q.put_nowait((event, payload))
                except Exception:
                    dead.append(q)
            for q in dead:
                queues.remove(q)

    @bp.route("/ai/tbcreate/draft/notify", methods=["POST"])
    def ai_tbcreate_draft_notify():
        """Receive a notification that Claude wrote/updated draft.json.

        Called by the tbcreate skill (curl from inside ttyd) after writing
        draft.json. Broadcasts an SSE event so the frontend auto-refreshes.
        """
        body = request.get_json(silent=True) or {}
        auth_user = session.get("auth_user") or {}
        owner_key = resolve_owner_key(
            body if isinstance(body, dict) else {}, auth_user
        )
        _sse_broadcast(owner_key, "draft_updated", {"ownerKey": owner_key})
        return ok({"notified": True})

    @bp.route("/ai/tbcreate/draft/events", methods=["GET"])
    def ai_tbcreate_draft_events():
        """SSE endpoint: frontend opens this to listen for draft updates.

        Query params: ownerKey (optional).
        Returns a streaming text/event-stream response.
        """
        payload = request.args.to_dict() or {}
        auth_user = session.get("auth_user") or {}
        owner_key = resolve_owner_key(
            payload if isinstance(payload, dict) else {}, auth_user
        )

        def generate():
            q: queue_module.Queue = queue_module.Queue()
            with _draft_sse_lock:
                _draft_sse_queues.setdefault(owner_key, []).append(q)
            try:
                yield "event: connected\ndata: {}\n\n"
                while True:
                    event, data = q.get()
                    yield f"event: {event}\ndata: {data}\n\n"
            except GeneratorExit:
                pass
            finally:
                with _draft_sse_lock:
                    queues = _draft_sse_queues.get(owner_key, [])
                    if q in queues:
                        queues.remove(q)

        return Response(
            stream_with_context(generate()),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )
