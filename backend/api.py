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


api_bp = Blueprint("api_b1", __name__, url_prefix="/api/b1")


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


#
@api_bp.route("/project/tasks/query", methods=["POST"])
def query_project_tasks():
    try:
        payload = request.get_json(silent=True) or {}
        if not (payload.get("userId") or payload.get("userid")):
            return _fail("missing userId", code=400, data={})
        if not (payload.get("projectId") or payload.get("projectid")):
            return _fail("missing projectId", code=400, data={})
        result = query_project_tasks_service(payload)
        if result.get("success"):
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


@api_bp.route("/tasks/query", methods=["POST"])
def query_user_tasks():
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

