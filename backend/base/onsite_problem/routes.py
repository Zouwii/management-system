"""现场问题跟踪 — API 路由."""

import time

from flask import request

from base.onsite_problem.sync import sync_onsite_full
from base.sync.lock import SyncBlocked, sync_guard, LOCK_ONSITE


def register(bp, ok, fail):
    @bp.route("/onsite/sync", methods=["POST"])
    def onsite_sync():
        """全量同步现场问题项目.

        POST body: { userId }
        流程: 拉列表 → 写 A 表 → 逐任务拉详情 → 写 B 表.
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
