"""数据库同步：A 表、B 表、全量下载"""

from flask import request

from services.task_sync_service import (
    sync_project_tasks_to_db,
    sync_task_detail_to_db,
    sync_task_details_batch_to_db,
)


def register(bp, ok, fail):
    @bp.route("/db/sync/project-tasks", methods=["POST"])
    def db_sync_project_tasks():
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
        try:
            payload = request.get_json(silent=True) or {}
            result = sync_task_details_batch_to_db(payload)
            if result.get("success"):
                return ok(result.get("data") or {})
            return fail(result.get("error", "batch sync failed"), code=400, data=result.get("data"))
        except Exception as e:
            return fail(str(e), code=500, data={})
