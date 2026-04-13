"""钉钉登录：网页 OAuth 回调、免登 get_token、会话 me/logout"""

import os
from urllib.parse import urlencode

from flask import redirect, request, session

from dingtalk_client import (
    build_dingtalk_oauth_url,
    exchange_dingtalk_auth_code,
    get_dingtalk_login_client_config,
    get_dingtalk_user_info,
    get_userid_by_unionid,
)
from services.auth_service import resolve_user_profile


def _build_redirect_uri():
    configured = str(os.getenv("DINGTALK_REDIRECT_URI") or "").strip()
    if configured:
        return configured
    return request.url_root.rstrip("/") + "/api/bt/auth/callback"


def _session_from_dingtalk_auth_code(auth_code: str, payload=None):
    auth_code = str(auth_code or "").strip()
    if not auth_code:
        return None, "missing auth code"

    token_out = exchange_dingtalk_auth_code(auth_code, payload=payload or {})
    if not token_out.get("ok"):
        return None, str(token_out.get("error") or "failed to exchange auth code")

    user_token = (token_out.get("data") or {}).get("accessToken")
    user_out = get_dingtalk_user_info(user_token)
    if not user_out.get("ok"):
        return None, str(user_out.get("error") or "failed to get dingtalk user info")

    user_data = dict(user_out.get("data") or {})
    # 某些登录链路只返回 unionId/openId，不含 userid。
    # 这里补一跳 getUseridByUnionid，确保能命中本地 user_character.user_id。
    if not str(user_data.get("userid") or "").strip() and str(user_data.get("unionId") or "").strip():
        print(
            "ZHR TEMP [auth] missing userid, try unionId->userid union_id={}".format(
                str(user_data.get("unionId") or "").strip()
            )
        )
        u2i_out = get_userid_by_unionid(user_data.get("unionId"))
        print(
            "ZHR TEMP [auth] unionId->userid result ok={} error={} data={}".format(
                u2i_out.get("ok"),
                u2i_out.get("error"),
                u2i_out.get("data"),
            )
        )
        if u2i_out.get("ok"):
            user_data["userid"] = (u2i_out.get("data") or {}).get("userid")
            print(
                "ZHR TEMP [auth] unionId->userid applied userid={}".format(
                    str(user_data.get("userid") or "").strip()
                )
            )
        else:
            print("ZHR TEMP [auth] unionId->userid failed, keep userid empty")

    profile_out = resolve_user_profile(user_data)
    if not profile_out.get("ok"):
        return None, str(profile_out.get("error") or "unauthorized account")

    profile = profile_out.get("profile")
    print("ZHR TEMP [auth] session profile role={} user_id={} teamId={}".format(
    (profile or {}).get("role"),
    (profile or {}).get("user_id"),
    (profile or {}).get("teamId"),
    ))
    session["auth_user"] = profile
    session.permanent = True
    return profile, None


def register(bp, ok, fail):
    @bp.route("/auth/dingtalk/url", methods=["GET"])
    def auth_dingtalk_url():
        try:
            login_config = get_dingtalk_login_client_config()
            out = build_dingtalk_oauth_url(
                redirect_uri=_build_redirect_uri(),
                state=str(request.args.get("state") or "").strip(),
            )
            if not out.get("ok"):
                return fail(out.get("error", "failed to build auth url"), code=400, data={})
            return ok(
                {
                    "url": out.get("url"),
                    "corpId": login_config.get("corpId", ""),
                    "clientId": login_config.get("clientId", ""),
                }
            )
        except Exception as e:
            return fail(str(e), code=500, data={})

    @bp.route("/auth/callback", methods=["GET"])
    def auth_dingtalk_callback():
        auth_code = (request.args.get("authCode") or request.args.get("code") or "").strip()
        if not auth_code:
            return fail("missing authCode", code=400, data={})

        try:
            _, err = _session_from_dingtalk_auth_code(auth_code)
            if err:
                query = urlencode({"auth_error": err})
                return redirect(f"/login?{query}")
            return redirect("/")
        except Exception as e:
            query = urlencode({"auth_error": str(e)})
            return redirect(f"/login?{query}")

    @bp.route("/auth/get_token", methods=["POST"])
    def auth_get_token():
        try:
            payload = request.get_json(silent=True) or {}
            auth_code = str(payload.get("code") or payload.get("authCode") or "").strip()
            # 钉钉免登里 clientId == appKey，支持前端按 requestAuthCode 参数透传 clientId。
            profile, err = _session_from_dingtalk_auth_code(auth_code, payload=payload)
            if err:
                return fail(err, code=400, data={})
            return ok({"user": profile})
        except Exception as e:
            return fail(str(e), code=500, data={})

    @bp.route("/auth/me", methods=["GET"])
    def auth_me():
        user = session.get("auth_user")
        if not user:
            return fail("unauthenticated", code=401, data={})
        return ok(user)

    @bp.route("/auth/logout", methods=["POST"])
    def auth_logout():
        session.pop("auth_user", None)
        return ok({"success": True})
