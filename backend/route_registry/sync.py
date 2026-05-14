"""Task data synchronization routes (merged from updates.py + db_sync.py).

Endpoints:
  GET  /update_lock_status          - Check if an update lock is held
  POST /time_range_update           - Sync A+B tables for a time range
  POST /full_update                 - Full update: A + threaded B/C
  POST /db/sync/project-tasks       - Sync A table (project task list)
  POST /db/sync/task-detail         - Sync a single B table record
  POST /db/sync/task-details-batch  - Batch sync B table records
"""

import time

from flask import request

from services.sync_lock import (
    _acquire_update_lock,
    _get_update_lock_status,
    _release_update_lock,
    DEFAULT_UPDATE_LOCK_KEY,
)
from services.task_sync_service import (
    full_update_service,
    sync_project_details_in_time_range_service,
    sync_project_tasks_to_db,
    sync_task_detail_to_db,
    sync_task_details_batch_to_db,
)


def register(bp, ok, fail):
    """Register all task sync routes on the given Blueprint."""

    # -- Lock management --

    @bp.route("/update_lock_status", methods=["GET"])
    def update_lock_status():
        """Check whether the global update lock is currently held."""
        try:
            status = _get_update_lock_status(DEFAULT_UPDATE_LOCK_KEY)
            return ok(status)
        except Exception as e:
            return fail(str(e), code=500, data={})

    # -- High-level sync operations --

    @bp.route("/time_range_update", methods=["POST"])
    def time_range_update():
        """Sync A+B tables for a specific time range (does not update C).

        Request body: userId, projectId, startDate, endDate.
        """
        try:
            payload = request.get_json(silent=True) or {}
            out = sync_project_details_in_time_range_service(payload)
            if out.get("success"):
                return ok(out.get("data") or {})
            return fail(out.get("error", "time_range_update failed"), code=400, data=out.get("data") or {})
        except Exception as e:
            return fail(str(e), code=500, data={})

    @bp.route("/full_update", methods=["POST"])
    def full_update():
        """Full update: update_endtime → compute range (last year) → sync A → threaded B/C.

        Request body: userId, projectId. Optional: maxResults, maxPages, workHourFieldId, force_refresh.
        """
        try:
            payload = request.get_json(silent=True) or {}
            user_id = str(payload.get("userId") or payload.get("userid") or "").strip()
            owner = "{}@{}".format(user_id or "unknown", int(time.time()))
            lock = _acquire_update_lock(DEFAULT_UPDATE_LOCK_KEY, owner)
            if not lock.get("ok"):
                return fail(lock.get("error", "update is in progress"), code=409, data=lock.get("lock") or {})
            try:
                out = full_update_service(payload)
                if out.get("success"):
                    return ok(out.get("data") or {})
                return fail(out.get("error", "full_update failed"), code=400, data=out.get("data") or {})
            finally:
                _release_update_lock(DEFAULT_UPDATE_LOCK_KEY, owner)
        except Exception as e:
            return fail(str(e), code=500, data={})

    # -- Low-level DB sync operations --

    @bp.route("/db/sync/project-tasks", methods=["POST"])
    def db_sync_project_tasks():
        """Sync A table: fetch and persist project task list from DingTalk.

        Request body: userId, projectId.
        """
        try:
            payload = request.get_json(silent=True) or {}
            if not (payload.get("userId") or payload.get("userid")):
                return fail("missing userId", code=400, data={})
            if not (payload.get("projectId") or payload.get("projectid")):
                return fail("missing projectId", code=400, data={})
            result = sync_project_tasks_to_db(payload)
            if result.get("success"):
                return ok(result.get("data") or {})
            return fail(result.get("error", "sync project tasks failed"), code=400, data=result.get("data"))
        except Exception as e:
            return fail(str(e), code=500, data={})

    @bp.route("/db/sync/task-detail", methods=["POST"])
    def db_sync_task_detail():
        """Sync B table: fetch and persist a single task detail from DingTalk.

        Request body: userId, taskId.
        """
        try:
            payload = request.get_json(silent=True) or {}
            if not (payload.get("userId") or payload.get("userid")):
                return fail("missing userId", code=400, data={})
            if not payload.get("taskId"):
                return fail("missing taskId", code=400, data={})
            result = sync_task_detail_to_db(payload)
            if result.get("success"):
                return ok(result.get("data") or {})
            return fail(result.get("error", "sync task detail failed"), code=400, data=result.get("data"))
        except Exception as e:
            return fail(str(e), code=500, data={})

    @bp.route("/db/sync/task-details-batch", methods=["POST"])
    def db_sync_task_details_batch():
        """Batch sync B table records from an in-memory task list."""
        try:
            payload = request.get_json(silent=True) or {}
            result = sync_task_details_batch_to_db(payload)
            if result.get("success"):
                return ok(result.get("data") or {})
            return fail(result.get("error", "batch sync failed"), code=400, data=result.get("data"))
        except Exception as e:
            return fail(str(e), code=500, data={})
