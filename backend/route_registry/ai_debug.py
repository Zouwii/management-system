"""AI ttyd session routes."""

import hashlib
import json
import os
import signal
import socket
import subprocess
import threading
import time
from pathlib import Path

from flask import request, session

_AI_CONFIG_PATH = Path(__file__).resolve().parent.parent / "ai" / "config.json"
_EASY_START_JZ_SCRIPT = Path(__file__).resolve().parent.parent / "easy_start_claude_jz"
_RUNTIME_DIR = Path(__file__).resolve().parent.parent / "runtime"
_SHARED_CLAUDE_DIR = _RUNTIME_DIR / "shared" / ".claude"
_USERS_ROOT = _RUNTIME_DIR / "users"
_LOG_FILE = _RUNTIME_DIR / "logs" / "ai_debug_subprocess.log"
_DEFAULT_OWNER_KEY = "anonymous"
_DEFAULT_TTYD_PORT_BASE = 8800
_DEFAULT_TTYD_PORT_SPAN = 400
_TTYD_SESSIONS = {}
_TTYD_LOCK = threading.Lock()


def _ensure_dirs() -> None:
    (_RUNTIME_DIR / "logs").mkdir(parents=True, exist_ok=True)
    _SHARED_CLAUDE_DIR.mkdir(parents=True, exist_ok=True)
    (_SHARED_CLAUDE_DIR / "skills").mkdir(parents=True, exist_ok=True)
    (_SHARED_CLAUDE_DIR / "plugins").mkdir(parents=True, exist_ok=True)
    _USERS_ROOT.mkdir(parents=True, exist_ok=True)


def _append_log(entry: dict) -> None:
    _ensure_dirs()
    with _LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _load_ai_config() -> dict:
    try:
        raw = _AI_CONFIG_PATH.read_text(encoding="utf-8")
        data = json.loads(raw) if raw.strip() else {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _safe_owner_key(owner_key: str) -> str:
    raw = str(owner_key or "").strip() or _DEFAULT_OWNER_KEY
    return hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()[:24]


def _resolve_owner_key(payload: dict) -> str:
    direct = str((payload or {}).get("ownerKey") or "").strip()
    if direct:
        return direct
    auth_user = session.get("auth_user") or {}
    if isinstance(auth_user, dict):
        for k in ("user_id", "userid", "name"):
            val = str(auth_user.get(k) or "").strip()
            if val:
                return val
    return _DEFAULT_OWNER_KEY


def _resolve_owner_name() -> str:
    auth_user = session.get("auth_user") or {}
    if isinstance(auth_user, dict):
        for k in ("name", "nick", "nickname", "user_name"):
            val = str(auth_user.get(k) or "").strip()
            if val:
                return val
    return ""


def _user_workspace(owner_key: str) -> dict:
    safe = _safe_owner_key(owner_key)
    user_root = _USERS_ROOT / safe
    claude_dir = user_root / ".claude"
    workspace_dir = user_root / "workspaces" / "default"
    return {
        "owner_safe": safe,
        "user_root": str(user_root),
        "claude_dir": str(claude_dir),
        "workspace_dir": str(workspace_dir),
        "shared_claude_dir": str(_SHARED_CLAUDE_DIR),
    }


def _make_env(owner_key: str, owner_name: str, model: str) -> dict:
    cfg = _load_ai_config()
    api_key = str(cfg.get("api_key") or "").strip()
    base_url = str(cfg.get("base_url") or "").strip()
    if not api_key:
        raise RuntimeError("missing ai/config.json api_key")

    env = os.environ.copy()
    real_home = str(os.environ.get("HOME") or "").strip()
    env["ANTHROPIC_API_KEY"] = api_key
    env["ANTHROPIC_BASE_URL"] = base_url
    env["ANTHROPIC_MODEL"] = model
    env["AI_OWNER_KEY"] = owner_key
    env["AI_OWNER_NAME"] = owner_name
    env["AI_USERS_ROOT"] = str(_USERS_ROOT)
    env["AI_SHARED_CLAUDE_DIR"] = str(_SHARED_CLAUDE_DIR)
    env["AI_SAFE_OWNER"] = _safe_owner_key(owner_key)
    path_items = [p for p in str(env.get("PATH") or "").split(":") if p]
    for candidate in (
        f"{real_home}/.nvm/versions/node/v20.20.2/bin" if real_home else "",
        f"{real_home}/.local/bin" if real_home else "",
    ):
        c = str(candidate or "").strip()
        if c and c not in path_items:
            path_items.append(c)
    env["PATH"] = ":".join(path_items)
    return env


def _normalize_owner_for_port(owner_key: str) -> int:
    seed = owner_key.encode("utf-8", errors="ignore")
    return sum(seed) % _DEFAULT_TTYD_PORT_SPAN


def _owner_ttyd_port(owner_key: str) -> int:
    base_raw = str(os.getenv("AI_TTYD_PORT_BASE", str(_DEFAULT_TTYD_PORT_BASE))).strip()
    span_raw = str(os.getenv("AI_TTYD_PORT_SPAN", str(_DEFAULT_TTYD_PORT_SPAN))).strip()
    try:
        base = int(base_raw)
    except Exception:
        base = _DEFAULT_TTYD_PORT_BASE
    try:
        span = max(int(span_raw), 50)
    except Exception:
        span = _DEFAULT_TTYD_PORT_SPAN
    return int(base + (_normalize_owner_for_port(owner_key) % span))


def _is_port_available(host: str, port: int) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((host, int(port)))
        return True
    except OSError:
        return False
    finally:
        try:
            sock.close()
        except Exception:
            pass


def _resolve_ttyd_port(owner_key: str) -> int:
    base_raw = str(os.getenv("AI_TTYD_PORT_BASE", str(_DEFAULT_TTYD_PORT_BASE))).strip()
    span_raw = str(os.getenv("AI_TTYD_PORT_SPAN", str(_DEFAULT_TTYD_PORT_SPAN))).strip()
    try:
        base = int(base_raw)
    except Exception:
        base = _DEFAULT_TTYD_PORT_BASE
    try:
        span = max(int(span_raw), 50)
    except Exception:
        span = _DEFAULT_TTYD_PORT_SPAN
    preferred = _owner_ttyd_port(owner_key)
    for i in range(span):
        candidate = int(base + ((preferred - base + i) % span))
        if _is_port_available("127.0.0.1", candidate):
            return candidate
    return preferred


def _terminate_ttyd_locked(state: dict) -> None:
    proc = state.get("proc")
    if proc is not None and proc.poll() is None:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except Exception:
            pass


def _build_ttyd_embed_url(port: int, owner_key: str, model: str) -> str:
    tpl = str(os.getenv("AI_TTYD_BASE_URL") or "").strip()
    if not tpl:
        tpl = "http://127.0.0.1:{port}/"
    tpl = tpl.replace("{port/}", "{port}/")
    if "{port}" in tpl:
        url = tpl.replace("{port}", str(port))
    else:
        url = tpl
    joiner = "&" if "?" in url else "?"
    return f"{url}{joiner}ownerKey={owner_key}&model={model}"


def _ensure_ttyd_session(owner_key: str, owner_name: str, model: str) -> dict:
    with _TTYD_LOCK:
        existing = _TTYD_SESSIONS.get(owner_key)
        if existing and existing["proc"].poll() is None:
            return existing
        if existing:
            _terminate_ttyd_locked(existing)
            _TTYD_SESSIONS.pop(owner_key, None)

        resolved_env = _make_env(owner_key=owner_key, owner_name=owner_name, model=model)
        port = _resolve_ttyd_port(owner_key)
        cmd = [
            "ttyd",
            "-i",
            "127.0.0.1",
            "-p",
            str(port),
            "bash",
            str(_EASY_START_JZ_SCRIPT),
        ]
        try:
            proc = subprocess.Popen(
                cmd,
                env=resolved_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True,
            )
        except FileNotFoundError as exc:
            raise RuntimeError("ttyd command not found in PATH") from exc

        time.sleep(0.3)
        if proc.poll() is not None:
            err = ""
            try:
                _out, err = proc.communicate(timeout=0.2)
            except Exception:
                pass
            raise RuntimeError(f"failed to start ttyd: {err.strip() or 'unknown error'}")

        ws = _user_workspace(owner_key)
        state = {
            "owner_key": owner_key,
            "owner_safe": ws["owner_safe"],
            "model": model,
            "port": port,
            "proc": proc,
            "created_at": int(time.time()),
        }
        _TTYD_SESSIONS[owner_key] = state
        _append_log(
            {
                "ts": int(time.time()),
                "phase": "ttyd_session_start",
                "owner_key": owner_key,
                "owner_safe": ws["owner_safe"],
                "model": model,
                "port": port,
                "pid": proc.pid,
            }
        )
        return state


def register(bp, ok, fail):
    def _handle_models():
        cfg = _load_ai_config()
        model = str(cfg.get("model") or "glm-5.1").strip() or "glm-5.1"
        return ok({"models": [{"name": model, "description": "default model"}]})

    def _handle_session_end():
        payload = request.get_json(silent=True) or {}
        owner_key = _resolve_owner_key(payload)
        with _TTYD_LOCK:
            ttyd_state = _TTYD_SESSIONS.pop(owner_key, None)
            if ttyd_state:
                _terminate_ttyd_locked(ttyd_state)
                _append_log(
                    {
                        "ts": int(time.time()),
                        "phase": "ttyd_session_end",
                        "owner_key": owner_key,
                        "port": ttyd_state.get("port"),
                    }
                )
        return ok({"ended": True, "ownerKey": owner_key})

    def _handle_ttyd_session():
        payload = request.get_json(silent=True) or {}
        owner_key = _resolve_owner_key(payload)
        owner_name = _resolve_owner_name()
        cfg = _load_ai_config()
        model = str(payload.get("model") or cfg.get("model") or "glm-5.1").strip() or "glm-5.1"
        try:
            state = _ensure_ttyd_session(owner_key=owner_key, owner_name=owner_name, model=model)
        except Exception as exc:
            return fail(str(exc), code=500, data={})
        ws = _user_workspace(owner_key)
        embed_url = _build_ttyd_embed_url(
            port=int(state.get("port") or _owner_ttyd_port(owner_key)),
            owner_key=owner_key,
            model=model,
        )
        return ok(
            {
                "embedUrl": embed_url,
                "ownerKey": owner_key,
                "ownerSafe": ws["owner_safe"],
                "userRoot": ws["user_root"],
                "workspaceDir": ws["workspace_dir"],
                "model": model,
                "port": int(state.get("port") or 0),
                "pid": int(state.get("proc").pid) if state.get("proc") else 0,
            }
        )

    def _handle_cache_current():
        payload = request.get_json(silent=True) or {}
        owner_key = _resolve_owner_key(payload)
        ws = _user_workspace(owner_key)
        return ok(
            {
                "ownerKey": owner_key,
                "ownerSafe": ws["owner_safe"],
                "userRoot": ws["user_root"],
                "workspaceDir": ws["workspace_dir"],
                "sharedClaudeDir": ws["shared_claude_dir"],
            }
        )

    @bp.route("/ai/models", methods=["GET"])
    def ai_models():
        return _handle_models()

    @bp.route("/ai/interactive/models", methods=["GET"])
    def ai_interactive_models():
        return _handle_models()

    @bp.route("/ai/chat/session_end", methods=["POST"])
    def ai_chat_session_end():
        return _handle_session_end()

    @bp.route("/ai/ttyd/session", methods=["POST"])
    def ai_ttyd_session():
        return _handle_ttyd_session()

    @bp.route("/ai/cache/current", methods=["GET", "POST"])
    def ai_cache_current():
        return _handle_cache_current()

