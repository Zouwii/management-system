"""现场问题跟踪 — API 路由."""

import time

from flask import request

from base.onsite_problem.sync import (
    sync_onsite_a_table,
    sync_onsite_b_table_via_proxy,
    sync_onsite_full,
    reset_onsite_a_cursor,
    get_onsite_a_cursor_status,
)
from base.onsite_problem.tb_proxy import check_proxy_health, update_proxy_credentials
from base.sync.lock import SyncBlocked, sync_guard, LOCK_ONSITE


def register(bp, ok, fail):
    @bp.route("/onsite/sync-a", methods=["POST"])
    def onsite_sync_a():
        """仅同步 A 表（断点续拉），不触发 B 表.

        POST body: { userId, [force_refresh] }
        断点续拉：若 Config 表存有游标则接着上次翻页；force_refresh=True 时从头拉.
        """
        try:
            payload = request.get_json(silent=True) or {}
            if not (payload.get("userId") or payload.get("userid")):
                return fail("missing userId", code=400, data={})

            owner = "onsite-a@{}".format(int(time.time()))
            with sync_guard(LOCK_ONSITE, owner):
                result = sync_onsite_a_table(payload)
                if result.get("success"):
                    return ok(result.get("data") or {})
                return fail(result.get("error", "A sync failed"), code=400, data=result.get("data") or {})
        except SyncBlocked as e:
            return fail(str(e), code=503, data={})
        except Exception as e:
            return fail(str(e), code=500, data={})

    @bp.route("/onsite/sync-b", methods=["POST"])
    def onsite_sync_b():
        """仅同步 B 表（TB Open API via proxy，多线程）.

        POST body: { userId, [thread_count=5], [skip_existing=false] }
        流程: 读 A 表所有 task → 代理 API 拉详情+评论+附件 → 写 B 表.
        skip_existing=true 时跳过 B 表已有记录.
        """
        try:
            payload = request.get_json(silent=True) or {}
            user_id = str(payload.get("userId") or payload.get("userid") or "").strip()
            if not user_id:
                return fail("missing userId", code=400, data={})

            thread_count = int(payload.get("thread_count", 5))
            skip_existing = bool(payload.get("skip_existing", False))

            owner = "onsite-b@{}".format(int(time.time()))
            with sync_guard(LOCK_ONSITE, owner):
                result = sync_onsite_b_table_via_proxy(
                    user_id, thread_count=thread_count, skip_existing=skip_existing
                )
                if result.get("success"):
                    return ok(result.get("data") or {})
                return fail(result.get("error", "B sync failed"), code=400, data=result.get("data") or {})
        except SyncBlocked as e:
            return fail(str(e), code=503, data={})
        except Exception as e:
            return fail(str(e), code=500, data={})

    @bp.route("/onsite/sync", methods=["POST"])
    def onsite_sync():
        """全量同步现场问题项目.

        POST body: { userId }
        流程: 拉列表 → 写 A 表 → TB Open API via proxy 写 B 表（含评论+附件）.
        """
        try:
            payload = request.get_json(silent=True) or {}
            if not (payload.get("userId") or payload.get("userid")):
                return fail("missing userId", code=400, data={})

            owner = "onsite@{}".format(int(time.time()))
            with sync_guard(LOCK_ONSITE, owner):
                result = sync_onsite_full(payload)
                if result.get("success"):
                    return ok(result.get("data") or {})
                return fail(result.get("error", "sync failed"), code=400, data=result.get("data") or {})
        except SyncBlocked as e:
            return fail(str(e), code=503, data={})
        except Exception as e:
            return fail(str(e), code=500, data={})

    @bp.route("/onsite/check-proxy", methods=["GET", "POST"])
    def onsite_check_proxy():
        """检查 TB Open API 代理凭据是否有效."""
        ok_flag, msg = check_proxy_health()
        return (fail(msg, code=503, data={"healthy": False})
                if not ok_flag
                else ok({"healthy": True, "message": msg}))

    @bp.route("/onsite/update-proxy", methods=["POST"])
    def onsite_update_proxy():
        """更新 TB Open API 代理凭据.

        POST body: { proxyToken, unionId }
        凭据将持久化到 data/tb_proxy_credentials.json, 优先级高于 .env.
        """
        try:
            payload = request.get_json(silent=True) or {}
            token = str(payload.get("proxyToken") or "").strip()
            union_id = str(payload.get("unionId") or "").strip()
            if not token or not union_id:
                return fail("missing proxyToken or unionId", code=400, data={})
            ok_flag, msg = update_proxy_credentials(token, union_id)
            if not ok_flag:
                return fail(msg, code=500, data={})
            # Verify the new credentials work
            healthy, hmsg = check_proxy_health()
            return ok({
                "updated": True,
                "healthy": healthy,
                "message": hmsg if not healthy else "凭据已更新且验证通过",
            })
        except Exception as e:
            return fail(str(e), code=500, data={})

    @bp.route("/onsite/cursor", methods=["GET"])
    def onsite_cursor():
        """查询 A 表同步游标状态（断点续拉进度）."""
        try:
            result = get_onsite_a_cursor_status()
            return ok(result.get("data") or {})
        except Exception as e:
            return fail(str(e), code=500, data={})

    @bp.route("/onsite/reset-cursor", methods=["POST"])
    def onsite_reset_cursor():
        """重置 A 表同步游标，下次同步从头开始."""
        try:
            result = reset_onsite_a_cursor()
            return ok(result.get("data") or {})
        except Exception as e:
            return fail(str(e), code=500, data={})

    @bp.route("/onsite/force-unlock", methods=["POST"])
    def onsite_force_unlock():
        """强制释放现场问题同步锁（用于异常中断后恢复）."""
        try:
            from base.sync.lock import LOCK_ONSITE, get_update_lock_status
            from base.db.engine import SessionLocal
            from base.db.orm import UpdateLock
            sess = SessionLocal()
            try:
                row = sess.query(UpdateLock).filter(UpdateLock.lock_key == LOCK_ONSITE).first()
                if row:
                    sess.delete(row)
                    sess.commit()
                    return ok({"released": True, "lock_key": LOCK_ONSITE, "previous_owner": str(getattr(row, "owner", ""))})
                return ok({"released": False, "message": "no lock found"})
            except Exception as e:
                sess.rollback()
                return fail(str(e), code=500)
            finally:
                sess.close()
        except Exception as e:
            return fail(str(e), code=500, data={})
