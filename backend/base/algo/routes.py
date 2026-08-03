"""算法组四张 A/B 表的手动同步路由。"""
from flask import request

from base.algo.sync import sync_algo_all
from base.config.service import is_sync_enabled
from base.sync.lock import sync_guard, SyncBlocked

LOCK_ALGO = "algo_sync:all"


def register(bp, ok, fail):
    @bp.route("/algo/sync_all", methods=["POST"])
    def algo_sync_all():
        """手动同步算法开发、算法问题两个项目的 A/B 表。"""
        if not is_sync_enabled():
            return fail("all DingTalk API calls are temporarily blocked (hard limit)", code=503, data={})
        try:
            import time
            payload = request.get_json(silent=True) or {}
            with sync_guard(LOCK_ALGO, "algo_sync@{}".format(int(time.time()))):
                result = sync_algo_all(payload)
                if result.get("success"):
                    return ok(result.get("data") or {})
                return fail(
                    result.get("error", "algo sync failed"),
                    code=400,
                    data=result.get("data") or {},
                )
        except SyncBlocked as e:
            return fail(str(e), code=503, data={})
        except Exception as e:
            return fail(str(e), code=500, data={})
