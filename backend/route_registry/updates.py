"""更新入口：time_range_update / full_update（按钮专用 API）。"""

import time

from flask import request

from services.task_sync_service import (
    _acquire_update_lock,
    _release_update_lock,
    DEFAULT_UPDATE_LOCK_KEY,
    full_update_service,
    sync_project_details_in_time_range_service,
)


def register(bp, ok, fail):
    @bp.route("/time_range_update", methods=["POST"])
    def time_range_update():
        """
        按 payload.startDate/endDate 同步 A+B（不更新 C）。
        预期入参：
        - userId
        - projectId
        - startDate
        - endDate
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
        """
        全量更新：update_endtime -> 计算(最近一年) -> 同步 A -> 3 线程同步 B/C。
        预期入参：
        - userId
        - projectId
        可选：
        - maxResults / maxPages / workHourFieldId / force_refresh
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

