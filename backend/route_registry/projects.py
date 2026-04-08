"""项目任务：搜索、列表查询、用户任务明细"""

import time

from flask import request

from services.project_task_service import (
    query_project_tasks_service,
    query_user_tasks_service,
    search_project_tasks_service,
)
from services.task_sync_service import (
    _acquire_update_lock,
    _release_update_lock,
    DEFAULT_UPDATE_LOCK_KEY,
    normal_incremental_update_service,
    sync_project_details_in_time_range_service,
    sync_project_tasks_to_db,
)


def register(bp, ok, fail):
    @bp.route("/project/tasks/search", methods=["POST"])
    def search_project_tasks():
        try:
            payload = request.get_json(silent=True) or {}
            if not (payload.get("userId") or payload.get("userid")):
                return fail("missing userId", code=400, data={})
            result = search_project_tasks_service(payload)
            if result.get("success"):
                return ok(result)
            return fail(result.get("error", "search project tasks failed"), code=400, data=result)
        except Exception as e:
            return fail(str(e), code=500, data={})

    @bp.route("/query_project_tasks", methods=["POST"])
    def query_project_tasks():
        try:
            payload = request.get_json(silent=True) or {}
            if not (payload.get("userId") or payload.get("userid")):
                return fail("missing userId", code=400, data={})
            if not (payload.get("projectId") or payload.get("projectid")):
                return fail("missing projectId", code=400, data={})
            if str(payload.get("sync_ab_by_config_time_range") or "").strip().lower() in {"1", "true", "yes", "on"}:
                user_id = str(payload.get("userId") or payload.get("userid") or "").strip()
                owner = "{}@{}".format(user_id or "unknown", int(time.time()))
                lock = _acquire_update_lock(DEFAULT_UPDATE_LOCK_KEY, owner)
                if not lock.get("ok"):
                    return fail(lock.get("error", "update is in progress"), code=409, data=lock.get("lock") or {})
                try:
                    out = normal_incremental_update_service(payload)
                    if out.get("success"):
                        return ok(out.get("data") or {})
                    return fail(out.get("error", "sync failed"), code=400, data=out.get("data") or {})
                finally:
                    _release_update_lock(DEFAULT_UPDATE_LOCK_KEY, owner)
            if str(payload.get("sync_ab_by_time_range") or "").strip().lower() in {"1", "true", "yes", "on"}:
                out = sync_project_details_in_time_range_service(payload)
                if out.get("success"):
                    return ok(out.get("data") or {})
                return fail(out.get("error", "sync failed"), code=400, data=out.get("data") or {})

            result = query_project_tasks_service(payload)
            if result.get("success"):
                sync_out = sync_project_tasks_to_db(payload, query_result=result)
                meta = dict(result.get("meta") or {})
                if sync_out.get("success"):
                    meta["db_sync"] = sync_out.get("data")
                else:
                    meta["db_sync_error"] = sync_out.get("error", "db sync failed")
                result["meta"] = meta
                return ok(result)
            status_code = ((result.get("data") or {}).get("status_code")) or 400
            return fail(
                result.get("error", "query project tasks failed"),
                code=int(status_code),
                data=result,
            )
        except Exception as e:
            return fail(str(e), code=500, data={})

    @bp.route("/query_task_details", methods=["POST"])
    def query_task_details():
        try:
            payload = request.get_json(silent=True) or {}
            if not (payload.get("userId") or payload.get("userid")):
                return fail("missing userId", code=400, data={})
            result = query_user_tasks_service(payload)
            if result.get("success"):
                return ok(result)
            status_code = ((result.get("data") or {}).get("status_code")) or 400
            return fail(
                result.get("error", "query user tasks failed"),
                code=int(status_code),
                data=result,
            )
        except Exception as e:
            return fail(str(e), code=500, data={})
