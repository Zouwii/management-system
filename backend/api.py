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
    count_software_dev_tasks_in_config_last_year_service,
)
from services.config_service import (
    get_projectids_service,
    get_userids_service,
    get_workhour_coefficient_service,
    get_workhour_character_coefficients_service,
    get_user_character_service,
    get_time_range_service,
    update_time_range_service,
    touch_last_update_time_service,
    get_workhour_auto_calc_service,
    update_workhour_auto_calc_service,
)
from services.task_sync_service import (
    sync_project_tasks_to_db,
    sync_task_detail_to_db,
    sync_task_details_batch_to_db,
    all_time_download_service,
    sync_project_details_in_config_time_range_service,
)
from services.workhour_aggregate_service import executor_quarter_workhours_db_service


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
        # 若要求“按 config.start/end 同步 A+B”，直接走服务端封装逻辑
        if str(payload.get("sync_ab_by_config_time_range") or "").strip().lower() in {"1", "true", "yes", "on"}:
            out = sync_project_details_in_config_time_range_service(payload)
            if out.get("success"):
                return _ok(out.get("data") or {})
            return _fail(out.get("error", "sync failed"), code=400, data=out.get("data") or {})

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


@api_bp.route("/config/workhour_coefficient", methods=["GET"])
def get_config_workhour_coefficient():
    """读取数据库 config 表里的工时折算系数（默认 0.7）。"""
    try:
        return _ok(get_workhour_coefficient_service())
    except Exception as e:
        return _fail(str(e), code=500, data={})


@api_bp.route("/config/workhour_character_coefficients", methods=["GET"])
def get_config_workhour_character_coefficients():
    """读取数据库 config 表里的 character -> coefficient 映射。"""
    try:
        return _ok(get_workhour_character_coefficients_service())
    except Exception as e:
        return _fail(str(e), code=500, data={})


@api_bp.route("/config/user_character", methods=["GET"])
def get_config_user_character():
    """
    根据 userId 查询 user_character 表，并计算该用户 character 对应的工时系数。
    query 参数：userId / userid
    """
    try:
        user_id = request.args.get("userId") or request.args.get("userid") or ""
        if not user_id:
            return _fail("missing userId", code=400, data={})
        return _ok(get_user_character_service(user_id))
    except Exception as e:
        return _fail(str(e), code=500, data={})


@api_bp.route("/config/time_range", methods=["GET"])
def get_config_time_range():
    """读取 config 表里的 start_time / end_time / last_update_time。"""
    try:
        return _ok(get_time_range_service())
    except Exception as e:
        return _fail(str(e), code=500, data={})


@api_bp.route("/config/time_range", methods=["POST"])
def update_config_time_range():
    """
    更新 config 表里的 start_time / end_time。
    请求 JSON：{ start_time: string, end_time: string }
    """
    try:
        payload = request.get_json(silent=True) or {}
        start_time = payload.get("start_time") or payload.get("startTime") or ""
        end_time = payload.get("end_time") or payload.get("endTime") or ""
        return _ok(update_time_range_service(start_time, end_time))
    except Exception as e:
        return _fail(str(e), code=500, data={})


@api_bp.route("/config/touch_last_update_time", methods=["POST"])
def touch_config_last_update_time():
    """仅更新 config.last_update_time 为当前时间（用于“更新”按钮）。"""
    try:
        return _ok(touch_last_update_time_service())
    except Exception as e:
        return _fail(str(e), code=500, data={})


@api_bp.route("/config/workhour_auto_calc", methods=["GET"])
def get_workhour_auto_calc():
    try:
        return _ok(get_workhour_auto_calc_service())
    except Exception as e:
        return _fail(str(e), code=500, data={})


@api_bp.route("/config/workhour_auto_calc", methods=["POST"])
def update_workhour_auto_calc():
    try:
        payload = request.get_json(silent=True) or {}
        enabled = payload.get("enabled") or payload.get("enable") or False
        auto_time = payload.get("auto_time") or payload.get("time") or payload.get("autoCalcTime") or "09:00"
        return _ok(update_workhour_auto_calc_service(enabled=enabled, auto_time=auto_time))
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


@api_bp.route("/all_time_download", methods=["POST"])
def all_time_download():
    """
    all_time_download：下载“软件开发”场景下的项目任务全量到 A 表（project_tasks）。

    入参：
    - userId / userid：必填（钉钉列表接口 userId）
    - projectId / projectid：必填
    - maxResults/maxPages（可选）
    - query（可选，默认 ""）
    """
    try:
        payload = request.get_json(silent=True) or {}
        result = all_time_download_service(payload)
        if result.get("success"):
            return _ok(result.get("data") or {})
        return _fail(result.get("error", "all_time_download failed"), code=400, data=result.get("data"))
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


@api_bp.route("/stats/executor_quarter_workhours", methods=["POST"])
def stats_executor_quarter_workhours():
    """从数据库汇总季度工时 / 季度逾期（基于 config.start_time/end_time）。"""
    try:
        payload = request.get_json(silent=True) or {}
        result = executor_quarter_workhours_db_service(payload)
        if result.get("success"):
            return _ok(result.get("data") or {})
        return _fail(result.get("error", "quarter aggregate failed"), code=400, data=result.get("data"))
    except Exception as e:
        return _fail(str(e), code=500, data={})


@api_bp.route("/stats/software_dev_count_last_year", methods=["POST"])
def stats_software_dev_count_last_year():
    """
    统计：end_time 配置的一年前到 end_time 区间内，
    软件开发 scenarioFieldConfigId 的项目任务数量。
    """
    try:
        payload = request.get_json(silent=True) or {}
        result = count_software_dev_tasks_in_config_last_year_service(payload)
        if result.get("success"):
            return _ok(result.get("data") or {})
        return _fail(
            result.get("error", "count failed"),
            code=400,
            data=result.get("data") or {},
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

