"""HTTP routes for AI interactive terminal (ttyd + Claude CLI).

Endpoints:
  GET  /ai/models              - List available AI models
  GET  /ai/interactive/models  - List interactive AI models (alias)
  POST /ai/ttyd/session        - Create or reuse a ttyd terminal session
"""

from flask import request, session

from ai.terminal.session import (
    build_ttyd_embed_url,
    ensure_ttyd_session,
    load_ai_config,
    owner_ttyd_port,
    resolve_owner_key,
    resolve_owner_name,
    ttyd_ttl_seconds,
    user_workspace,
)


def register(bp, ok, fail):
    """Register AI terminal routes on the given Blueprint."""

    @bp.route("/ai/models", methods=["GET"])
    def ai_models():
        """List available AI models from the gateway config."""
        cfg = load_ai_config()
        model = str(cfg.get("model") or "glm-5.1").strip() or "glm-5.1"
        return ok({"models": [{"name": model, "description": "default model"}]})

    @bp.route("/ai/interactive/models", methods=["GET"])
    def ai_interactive_models():
        """List interactive AI models (alias for /ai/models)."""
        cfg = load_ai_config()
        model = str(cfg.get("model") or "glm-5.1").strip() or "glm-5.1"
        return ok({"models": [{"name": model, "description": "default model"}]})

    @bp.route("/ai/ttyd/session", methods=["POST"])
    def ai_ttyd_session():
        """Create or reuse a ttyd terminal session for the current user.

        Request body (optional): {"ownerKey": "...", "model": "...", "skill": "创建tb单"}
        Returns embedUrl, ownerKey, ownerSafe, userRoot, workspaceDir, model, port, pid.
        """
        payload = request.get_json(silent=True) or {}
        auth_user = session.get("auth_user") or {}
        owner_key = resolve_owner_key(payload, auth_user)
        owner_name = resolve_owner_name(auth_user)
        cfg = load_ai_config()
        model = str(payload.get("model") or cfg.get("model") or "glm-5.1").strip() or "glm-5.1"
        skill = str(payload.get("skill") or "").strip()
        try:
            state = ensure_ttyd_session(
                owner_key=owner_key, owner_name=owner_name, model=model,
                auth_user=auth_user, skill=skill,
            )
        except Exception as exc:
            return fail(str(exc), code=500, data={})
        ws = user_workspace(owner_key)
        embed_url = build_ttyd_embed_url(
            port=int(state.get("port") or owner_ttyd_port(owner_key)),
            owner_key=owner_key,
            model=model,
            skill=skill,
        )
        return ok(
            {
                "embedUrl": embed_url,
                "ownerKey": owner_key,
                "ownerSafe": ws["owner_safe"],
                "userRoot": ws["user_root"],
                "workspaceDir": ws["workspace_dir"],
                "model": model,
                "skill": skill,
                "port": int(state.get("port") or 0),
                "pid": int(state.get("proc").pid) if state.get("proc") else 0,
                "createdAt": int(state.get("created_at") or 0),
                "expiresAt": int(state.get("expires_at") or 0),
                "ttlSeconds": ttyd_ttl_seconds(),
            }
        )
