from flask import Blueprint, jsonify, request

from services.proxy_service import (
    dingtalk_gettoken_service,
    dingtalk_proxy_service,
    health_service,
)
from services.project_task_service import (
    query_project_tasks_service,
    query_user_tasks_service,
    search_project_tasks_service,
)
from services.config_service import get_projectids_service, get_userids_service
from services.task_sync_service import (
    sync_project_tasks_to_db,
    sync_task_detail_to_db,
    sync_task_details_batch_to_db,
)
from services.workhour_aggregate_service import executor_workhours_aggregate_service


api_bp = Blueprint("api_bt", __name__, url_prefix="/api/bt")


def _ok(data):
    return jsonify({"code": 200, "error": "", "data": data}), 200


def _fail(msg, code=400, data=None):
    return jsonify({"code": code, "error": msg, "data": data if data is not None else {}}), code


@api_bp.route("/health", methods=["GET"])
def health():
    try:
        return _ok(health_service())
    except Exception as e:
        return _fail(str(e), code=500, data={})


@api_bp.route("/proxy", methods=["POST"])
def proxy_dingtalk():
    try:
        payload = request.get_json(silent=True) or {}
        result = dingtalk_proxy_service(payload)
        if result.get("success"):
            return _ok(result)
        return _fail(result.get("error", "proxy failed"), code=400, data=result)
    except Exception as e:
        return _fail(str(e), code=500, data={})


@api_bp.route("/gettoken", methods=["GET", "POST"])
def gettoken():
    try:
        payload = request.get_json(silent=True) or {}
        result = dingtalk_gettoken_service(payload)
        if result.get("success"):
            return _ok(result)
        return _fail(result.get("error", "gettoken failed"), code=400, data=result)
    except Exception as e:
        return _fail(str(e), code=500, data={})


# 项目任务搜索
@api_bp.route("/project/tasks/search", methods=["POST"])
def search_project_tasks():
    try:
        payload = request.get_json(silent=True) or {}
        if not (payload.get("userId") or payload.get("userid")):
            return _fail("missing userId", code=400, data={})
        result = search_project_tasks_service(payload)
        if result.get("success"):
            return _ok(result)
        return _fail(result.get("error", "search project tasks failed"), code=400, data=result)
    except Exception as e:
        return _fail(str(e), code=500, data={})


@api_bp.route("/query_project_tasks", methods=["POST"])
def query_project_tasks():
    try:
        payload = request.get_json(silent=True) or {}
        if not (payload.get("userId") or payload.get("userid")):
            return _fail("missing userId", code=400, data={})
        if not (payload.get("projectId") or payload.get("projectid")):
            return _fail("missing projectId", code=400, data={})
        result = query_project_tasks_service(payload)
        if result.get("success"):
            # 与列表查询同一次钉钉结果：按 scenario 过滤后 upsert 到 project_tasks（A 表）
            sync_out = sync_project_tasks_to_db(payload, query_result=result)
            meta = dict(result.get("meta") or {})
            if sync_out.get("success"):
                meta["db_sync"] = sync_out.get("data")
            else:
                meta["db_sync_error"] = sync_out.get("error", "db sync failed")
            result["meta"] = meta
            return _ok(result)
        status_code = ((result.get("data") or {}).get("status_code")) or 400
        return _fail(
            result.get("error", "query project tasks failed"),
            code=int(status_code),
            data=result,
        )
    except Exception as e:
        return _fail(str(e), code=500, data={})


@api_bp.route("/config/userids", methods=["GET"])
def get_config_userids():
    try:
        return _ok(get_userids_service())
    except Exception as e:
        return _fail(str(e), code=500, data={})


@api_bp.route("/config/projectids", methods=["GET"])
def get_config_projectids():
    try:
        return _ok(get_projectids_service())
    except Exception as e:
        return _fail(str(e), code=500, data={})


@api_bp.route("/db/sync/project-tasks", methods=["POST"])
def db_sync_project_tasks():
    """列表同步 → A 表（仅保留 scenarioFieldConfigId 匹配，默认软件开发）。"""
    try:
        payload = request.get_json(silent=True) or {}
        if not (payload.get("userId") or payload.get("userid")):
            return _fail("missing userId", code=400, data={})
        if not (payload.get("projectId") or payload.get("projectid")):
            return _fail("missing projectId", code=400, data={})
        result = sync_project_tasks_to_db(payload)
        if result.get("success"):
            return _ok(result.get("data") or {})
        return _fail(result.get("error", "sync project tasks failed"), code=400, data=result.get("data"))
    except Exception as e:
        return _fail(str(e), code=500, data={})


@api_bp.route("/db/sync/task-detail", methods=["POST"])
def db_sync_task_detail():
    """单任务详情 → B 表（模式 1 覆盖）。"""
    try:
        payload = request.get_json(silent=True) or {}
        if not (payload.get("userId") or payload.get("userid")):
            return _fail("missing userId", code=400, data={})
        if not payload.get("taskId"):
            return _fail("missing taskId", code=400, data={})
        result = sync_task_detail_to_db(payload)
        if result.get("success"):
            return _ok(result.get("data") or {})
        return _fail(result.get("error", "sync task detail failed"), code=400, data=result.get("data"))
    except Exception as e:
        return _fail(str(e), code=500, data={})


@api_bp.route("/db/sync/task-details-batch", methods=["POST"])
def db_sync_task_details_batch():
    """批量单任务详情 → B 表。"""
    try:
        payload = request.get_json(silent=True) or {}
        result = sync_task_details_batch_to_db(payload)
        if result.get("success"):
            return _ok(result.get("data") or {})
        return _fail(result.get("error", "batch sync failed"), code=400, data=result.get("data"))
    except Exception as e:
        return _fail(str(e), code=500, data={})


@api_bp.route("/stats/executor_workhours", methods=["POST"])
def stats_executor_workhours():
    """服务端按执行者循环拉详情并汇总工时（单次请求，不在浏览器产生多条 API）。"""
    try:
        payload = request.get_json(silent=True) or {}
        result = executor_workhours_aggregate_service(payload)
        if result.get("success"):
            return _ok(result.get("data") or {})
        return _fail(
            result.get("error", "aggregate failed"),
            code=400,
            data=result.get("data"),
        )
    except Exception as e:
        return _fail(str(e), code=500, data={})


@api_bp.route("/query_task_details", methods=["POST"])
def query_task_details():
    try:
        payload = request.get_json(silent=True) or {}
        if not (payload.get("userId") or payload.get("userid")):
            return _fail("missing userId", code=400, data={})
        result = query_user_tasks_service(payload)
        if result.get("success"):
            return _ok(result)
        status_code = ((result.get("data") or {}).get("status_code")) or 400
        return _fail(
            result.get("error", "query user tasks failed"),
            code=int(status_code),
            data=result,
        )
    except Exception as e:
        return _fail(str(e), code=500, data={})

