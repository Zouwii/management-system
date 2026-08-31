"""钉钉登录：网页 OAuth 回调、免登 get_token、会话 me/logout、离线本地登录"""

import os
from urllib.parse import urlencode

from flask import redirect, request, session

from base.dingtalk_client import (
    build_dingtalk_oauth_url,
    get_dingtalk_login_client_config,
)
from base.auth.service import authenticate_dingtalk_user, authenticate_local_user


def _build_redirect_uri():
    configured = str(os.getenv("DINGTALK_REDIRECT_URI") or "").strip()
    if configured:
        return configured
    return request.url_root.rstrip("/") + "/api/bt/auth/callback"


def _session_from_dingtalk_auth_code(auth_code: str, payload=None):
    """Exchange DingTalk auth code and persist the resolved profile in session."""
    result = authenticate_dingtalk_user(auth_code, payload=payload)
    if not result.get("ok"):
        return None, str(result.get("error", "authentication failed"))
    profile = result.get("profile")
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

    @bp.route("/auth/local/users", methods=["GET"])
    def auth_local_users():
        """离线模式：返回本地 user_character 表中所有用户列表。"""
        try:
            from base.db.engine import SessionLocal
            from base.db.orm import UserCharacter as DbUserCharacter

            session_db = SessionLocal()
            try:
                rows = session_db.query(DbUserCharacter).order_by(DbUserCharacter.name).all()
                users = []
                for row in rows:
                    users.append({
                        "user_id": row.user_id,
                        "name": row.name or row.user_id,
                        "teamCode": str(row.team_code or ""),
                        "jobRoleCode": str(row.job_role_code or ""),
                    })
                return ok({"users": users})
            finally:
                session_db.close()
        except Exception as e:
            return fail(str(e), code=500, data={})

    @bp.route("/auth/local/login", methods=["POST"])
    def auth_local_login():
        """离线模式登录：user_id + password（固定 123456），建立 session。"""
        try:
            payload = request.get_json(silent=True) or {}
            user_id = str(payload.get("user_id") or payload.get("userId") or "").strip()
            password = str(payload.get("password") or "").strip()

            result = authenticate_local_user(user_id, password)
            if not result.get("ok"):
                return fail(result.get("error", "login failed"), code=400, data={})

            profile = result.get("profile")
            session["auth_user"] = profile
            session.permanent = True
            return ok(profile)
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
