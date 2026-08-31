"""配置：userids、projectids、工时系数、时间范围、自动计算"""

from flask import request

from base.config.service import (
    get_projectids_service,
    get_userids_service,
    get_workhour_role_coefficients_service,
    get_user_character_service,
    get_last_update_time_service,
    get_default_time_range_service,
    touch_last_update_time_service,
    update_endtime_service,
    get_workhour_auto_calc_service,
    update_workhour_auto_calc_service,
)


def register(bp, ok, fail):
    @bp.route("/config/userids", methods=["GET"])
    def get_config_userids():
        try:
            return ok(get_userids_service())
        except Exception as e:
            return fail(str(e), code=500, data={})

    @bp.route("/config/projectids", methods=["GET"])
    def get_config_projectids():
        try:
            return ok(get_projectids_service())
        except Exception as e:
            return fail(str(e), code=500, data={})

    @bp.route("/config/workhour_role_coefficients", methods=["GET"])
    def get_config_workhour_role_coefficients():
        try:
            return ok(get_workhour_role_coefficients_service())
        except Exception as e:
            return fail(str(e), code=500, data={})

    @bp.route("/config/user_character", methods=["GET"])
    def get_config_user_character():
        try:
            user_id = request.args.get("userId") or request.args.get("userid") or ""
            if not user_id:
                return fail("missing userId", code=400, data={})
            return ok(get_user_character_service(user_id))
        except Exception as e:
            return fail(str(e), code=500, data={})

    @bp.route("/config/last_update_time", methods=["GET"])
    def get_config_last_update_time():
        try:
            return ok(get_last_update_time_service())
        except Exception as e:
            return fail(str(e), code=500, data={})

    @bp.route("/config/default_time_range", methods=["GET"])
    def get_config_default_time_range():
        try:
            return ok(get_default_time_range_service())
        except Exception as e:
            return fail(str(e), code=500, data={})

    @bp.route("/config/touch_last_update_time", methods=["POST"])
    def touch_config_last_update_time():
        try:
            return ok(touch_last_update_time_service())
        except Exception as e:
            return fail(str(e), code=500, data={})

    @bp.route("/config/update_endtime", methods=["POST"])
    def update_config_endtime():
        try:
            out = update_endtime_service()
            if out.get("success"):
                return ok(out)
            return fail(out.get("error", "update end_time failed"), code=400, data=out.get("data") or {})
        except Exception as e:
            return fail(str(e), code=500, data={})

    @bp.route("/config/workhour_auto_calc", methods=["GET"])
    def get_workhour_auto_calc():
        try:
            return ok(get_workhour_auto_calc_service())
        except Exception as e:
            return fail(str(e), code=500, data={})

    @bp.route("/config/workhour_auto_calc", methods=["POST"])
    def update_workhour_auto_calc():
        try:
            payload = request.get_json(silent=True) or {}
            enabled = payload.get("enabled") or payload.get("enable") or False
            auto_time = payload.get("auto_time") or payload.get("time") or payload.get("autoCalcTime") or "09:00"
            return ok(update_workhour_auto_calc_service(enabled=enabled, auto_time=auto_time))
        except Exception as e:
            return fail(str(e), code=500, data={})
