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
    _upsert_config_value,
)
from base.config.service import is_sync_enabled, is_full_sync_enabled


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
                if not is_full_sync_enabled():
                    return fail("sync is temporarily disabled (offline mode)", code=503, data={})
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
                if not is_full_sync_enabled():
                    return fail("sync is temporarily disabled (offline mode)", code=503, data={})
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

    @bp.route("/sync_all_users", methods=["POST"])
    def sync_all_users():
        """同步 user_character 表中所有用户，使用同一个 last_update_time 快照。"""
        if not is_full_sync_enabled():
            return fail("sync is temporarily disabled (offline mode)", code=503, data={})

        owner = "sync_all@{}".format(int(time.time()))
        lock = _acquire_update_lock(DEFAULT_UPDATE_LOCK_KEY, owner)
        if not lock.get("ok"):
            return fail(lock.get("error", "update is in progress"), code=409, data=lock.get("lock") or {})

        try:
            from base.db.orm import UserCharacter as DbUserCharacter
            from base.db.engine import SessionLocal
            from base.config.service import get_config_projectids
            from base.api_monitor import BJ_TZ

            # 获取 project_id
            projectids = get_config_projectids() or {}
            project_id = str(next(iter(projectids.values())) or "").strip()
            if not project_id:
                return fail("missing projectId from config", code=400)

            # 获取所有用户
            sess = SessionLocal()
            try:
                rows = sess.query(DbUserCharacter.user_id).all()
                user_ids = [str(r[0]).strip() for r in rows if r and str(r[0]).strip()]
            finally:
                sess.close()

            if not user_ids:
                return fail("no users found in user_character", code=400)

            # 逐用户同步，skip_update_time=True 避免每个用户推进 last_update_time
            ok_count = 0
            fail_count = 0
            errors = []
            for uid in user_ids:
                out = normal_incremental_update_service(
                    {"userId": uid, "projectId": project_id},
                    skip_update_time=True,
                )
                if out.get("success"):
                    ok_count += 1
                else:
                    fail_count += 1
                    errors.append({"userId": uid, "error": out.get("error")})

            # 所有用户同步完成后，推进 last_update_time 一次
            now_bj = dt.now(BJ_TZ)
            _upsert_config_value("last_update_time", now_bj.isoformat())

            return ok({
                "beijing_now": now_bj.isoformat(),
                "user_count": len(user_ids),
                "ok": ok_count,
                "fail": fail_count,
                "errors": errors[:20],
            })
        finally:
            _release_update_lock(DEFAULT_UPDATE_LOCK_KEY, owner)

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
