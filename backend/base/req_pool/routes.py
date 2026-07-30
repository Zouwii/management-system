"""需求池 — API 路由."""

import time

from flask import request

from base.req_pool.sync import (
    sync_req_pool_a_table,
    sync_req_pool_b_table_via_proxy,
    sync_req_pool_full,
    reset_req_pool_a_cursor,
    get_req_pool_a_cursor_status,
)
from base.onsite_problem.tb_proxy import check_proxy_health, update_proxy_credentials
from base.sync.lock import SyncBlocked, sync_guard, LOCK_REQ_POOL


def register(bp, ok, fail):
    @bp.route("/req-pool/sync-a", methods=["POST"])
    def req_pool_sync_a():
        """仅同步 A 表（断点续拉），不触发 B 表.

        POST body: { userId, [force_refresh] }
        """
        try:
            payload = request.get_json(silent=True) or {}
            if not (payload.get("userId") or payload.get("userid")):
                return fail("missing userId", code=400, data={})

            owner = "reqpool-a@{}".format(int(time.time()))
            with sync_guard(LOCK_REQ_POOL, owner):
                result = sync_req_pool_a_table(payload)
                if result.get("success"):
                    return ok(result.get("data") or {})
                return fail(result.get("error", "A sync failed"), code=400, data=result.get("data") or {})
        except SyncBlocked as e:
            return fail(str(e), code=503, data={})
        except Exception as e:
            return fail(str(e), code=500, data={})

    @bp.route("/req-pool/sync-b", methods=["POST"])
    def req_pool_sync_b():
        """仅同步 B 表（TB Open API via proxy，多线程）.

        POST body: { userId, [thread_count=5], [skip_existing=false] }
        """
        try:
            payload = request.get_json(silent=True) or {}
            user_id = str(payload.get("userId") or payload.get("userid") or "").strip()
            if not user_id:
                return fail("missing userId", code=400, data={})

            thread_count = int(payload.get("thread_count", 5))
            skip_existing = bool(payload.get("skip_existing", False))

            owner = "reqpool-b@{}".format(int(time.time()))
            with sync_guard(LOCK_REQ_POOL, owner):
                result = sync_req_pool_b_table_via_proxy(
                    user_id, thread_count=thread_count, skip_existing=skip_existing
                )
                if result.get("success"):
                    return ok(result.get("data") or {})
                return fail(result.get("error", "B sync failed"), code=400, data=result.get("data") or {})
        except SyncBlocked as e:
            return fail(str(e), code=503, data={})
        except Exception as e:
            return fail(str(e), code=500, data={})

    @bp.route("/req-pool/sync", methods=["POST"])
    def req_pool_sync():
        """全量同步需求池项目.

        POST body: { userId }
        """
        try:
            payload = request.get_json(silent=True) or {}
            if not (payload.get("userId") or payload.get("userid")):
                return fail("missing userId", code=400, data={})

            owner = "reqpool@{}".format(int(time.time()))
            with sync_guard(LOCK_REQ_POOL, owner):
                result = sync_req_pool_full(payload)
                if result.get("success"):
                    return ok(result.get("data") or {})
                return fail(result.get("error", "sync failed"), code=400, data=result.get("data") or {})
        except SyncBlocked as e:
            return fail(str(e), code=503, data={})
        except Exception as e:
            return fail(str(e), code=500, data={})

    @bp.route("/req-pool/cursor", methods=["GET"])
    def req_pool_cursor():
        """查询 A 表同步游标状态."""
        try:
            result = get_req_pool_a_cursor_status()
            return ok(result.get("data") or {})
        except Exception as e:
            return fail(str(e), code=500, data={})

    @bp.route("/req-pool/reset-cursor", methods=["POST"])
    def req_pool_reset_cursor():
        """重置 A 表同步游标，下次同步从头开始."""
        try:
            result = reset_req_pool_a_cursor()
            return ok(result.get("data") or {})
        except Exception as e:
            return fail(str(e), code=500, data={})

    @bp.route("/req-pool/force-unlock", methods=["POST"])
    def req_pool_force_unlock():
        """强制释放需求池同步锁."""
        try:
            from base.sync.lock import LOCK_REQ_POOL as LOCK_RP
            from base.db.engine import SessionLocal
            from base.db.orm import UpdateLock
            sess = SessionLocal()
            try:
                row = sess.query(UpdateLock).filter(UpdateLock.lock_key == LOCK_RP).first()
                if row:
                    sess.delete(row)
                    sess.commit()
                    return ok({"released": True, "lock_key": LOCK_RP, "previous_owner": str(getattr(row, "owner", ""))})
                return ok({"released": False, "message": "no lock found"})
            except Exception as e:
                sess.rollback()
                return fail(str(e), code=500)
            finally:
                sess.close()
        except Exception as e:
            return fail(str(e), code=500, data={})
