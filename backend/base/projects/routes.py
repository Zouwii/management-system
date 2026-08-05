"""项目任务：列表查询、用户任务明细"""

import time
from datetime import datetime as dt

from flask import request, session

from base.projects.task_service import (
    query_project_tasks_service,
    query_user_tasks_service,
)
from base.sync.task_detail_extract import extract_task_detail_custom_fields_service
from base.sync.lock import (
    _acquire_update_lock,
    _release_update_lock,
    DEFAULT_UPDATE_LOCK_KEY,
)
from base.sync.task_sync import (
    normal_incremental_update_service,
    sync_project_details_in_time_range_service,
    sync_project_tasks_to_db,
)
from base.config.service import is_sync_enabled


def register(bp, ok, fail):
    def _require_login():
        user = session.get("auth_user")
        return user if isinstance(user, dict) else None

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

            # 硬限检查：阻止所有钉钉 API 调用（包括查询）
            if not is_sync_enabled():
                return fail("all DingTalk API calls are temporarily blocked (hard limit)", code=503, data={})

            result = query_project_tasks_service(payload)
            if result.get("success"):
                meta = dict(result.get("meta") or {})
                if is_sync_enabled():
                    sync_out = sync_project_tasks_to_db(payload, query_result=result)
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

    @bp.route("/increase_sync", methods=["POST"])
    def increase_sync():
        """增量同步：委托给 benti_team_incremental_update_service（去重优化版）。

        仅同步本体团队（team_id 0/1）20 人，列表及明细均跨成员去重，
        相比旧版"逐用户全量拉取"节省 80%+ API 调用量。
        """

        try:
            from base.sync.task_sync import benti_team_incremental_update_service
            from base.config.service import get_config_projectids

            projectids = get_config_projectids() or {}
            project_id = str(next(iter(projectids.values())) or "").strip()
            if not project_id:
                return fail("missing projectId from config", code=400)

            result = benti_team_incremental_update_service({"projectId": project_id})

            if not result.get("success"):
                return fail(
                    result.get("error", "benti incremental update failed"),
                    code=500,
                    data=result.get("data") or {},
                )

            data = result.get("data") or {}
            written = data.get("written") or {}
            return ok({
                "beijing_now": data.get("lastUpdateTime", ""),
                "user_count": data.get("memberCount", 0),
                "dev": {
                    "ok": data.get("memberCount", 0),
                    "fail": 0,
                },
                "issue": {
                    "ok": data.get("memberCount", 0),
                    "fail": 0,
                },
                "detail_count": data.get("detailCount", 0),
                "dev_written": written.get("dev", 0),
                "issue_written": written.get("issue", 0),
                "unique_task_count": data.get("uniqueTaskCount", 0),
                "skipped_executors": data.get("skippedExecutors", {}),
                "benti_optimized": True,
            })
        except Exception as e:
            return fail(str(e), code=500, data={})

    @bp.route("/query_task_details", methods=["POST"])
    def query_task_details():
        try:
            payload = request.get_json(silent=True) or {}
            if not (payload.get("userId") or payload.get("userid")):
                return fail("missing userId", code=400, data={})

            # 硬限检查：阻止所有钉钉 API 调用（包括查询）
            if not is_sync_enabled():
                return fail("all DingTalk API calls are temporarily blocked (hard limit)", code=503, data={})

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

    @bp.route("/query_task_detail_custom_fields", methods=["POST"])
    def query_task_detail_custom_fields():
        try:
            user = _require_login()
            if not user:
                return fail("unauthenticated", code=401, data={})
            payload = request.get_json(silent=True) or {}
            task_id = str(payload.get("taskId") or payload.get("task_id") or "").strip()
            project_id = str(payload.get("projectId") or payload.get("project_id") or "").strip()
            user_id = str(user.get("user_id") or user.get("userid") or "").strip()
            if not task_id:
                return fail("missing taskId", code=400, data={})
            result = extract_task_detail_custom_fields_service(
                user_id=user_id,
                task_id=task_id,
                project_id=project_id or None,
            )
            if result.get("success"):
                return ok(result)
            status_code = 404 if result.get("error") == "task detail not found" else 400
            return fail(result.get("error", "extract task detail custom fields failed"), code=status_code, data=result)
        except Exception as e:
            return fail(str(e), code=500, data={})
