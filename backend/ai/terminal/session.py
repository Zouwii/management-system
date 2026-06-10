"""AI terminal session manager.

Manages ttyd subprocess lifecycle: port allocation, process start/stop,
owner-key-based session isolation, and user workspace preparation.
"""

from __future__ import annotations

import hashlib
import json
import os
import signal
import socket
import subprocess
import threading
import time
from pathlib import Path

_AI_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"
_EASY_START_JZ_SCRIPT = Path(__file__).resolve().parent / "launcher.sh"
_RUNTIME_DIR = Path(__file__).resolve().parent.parent.parent / "runtime"
_SHARED_CLAUDE_DIR = _RUNTIME_DIR / "shared" / ".claude"
_USERS_ROOT = _RUNTIME_DIR / "users"
_LOG_FILE = _RUNTIME_DIR / "logs" / "ai_debug_subprocess.log"
_DEFAULT_OWNER_KEY = "anonymous"
_DEFAULT_TTYD_PORT_BASE = 8800
_DEFAULT_TTYD_PORT_SPAN = 400
_DEFAULT_TTYD_TTL_SECONDS = 2 * 60 * 60

_TTYD_SESSIONS: dict = {}
_TTYD_LOCK = threading.Lock()
_JANITOR_LOCK = threading.Lock()
_JANITOR_STARTED = False


def ensure_runtime_dirs() -> None:
    """Create all required runtime directories (logs, shared claude config, users root)."""
    (_RUNTIME_DIR / "logs").mkdir(parents=True, exist_ok=True)
    _SHARED_CLAUDE_DIR.mkdir(parents=True, exist_ok=True)
    (_SHARED_CLAUDE_DIR / "skills").mkdir(parents=True, exist_ok=True)
    (_SHARED_CLAUDE_DIR / "plugins").mkdir(parents=True, exist_ok=True)
    _USERS_ROOT.mkdir(parents=True, exist_ok=True)


def append_log(entry: dict) -> None:
    """Append a JSON log entry to the subprocess log file."""
    ensure_runtime_dirs()
    with _LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def ttyd_ttl_seconds() -> int:
    """Return the maximum lifetime for a ttyd session."""
    raw = str(os.getenv("AI_TTYD_TTL_SECONDS", str(_DEFAULT_TTYD_TTL_SECONDS))).strip()
    try:
        return max(int(raw), 60)
    except Exception:
        return _DEFAULT_TTYD_TTL_SECONDS


def load_ai_config() -> dict:
    """Load AI gateway configuration from ai/config.json."""
    try:
        raw = _AI_CONFIG_PATH.read_text(encoding="utf-8")
        data = json.loads(raw) if raw.strip() else {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def safe_owner_key(owner_key: str) -> str:
    """Hash an owner_key into a filesystem-safe 24-char hex string."""
    raw = str(owner_key or "").strip() or _DEFAULT_OWNER_KEY
    return hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()[:24]


def resolve_owner_key(payload: dict, session_auth: dict = None) -> str:
    """Resolve the effective owner_key from a request payload or session.

    Priority: explicit ownerKey in payload > auth_user.user_id > auth_user.name > 'anonymous'.
    """
    direct = str((payload or {}).get("ownerKey") or "").strip()
    if direct:
        return direct
    auth_user = session_auth or {}
    if isinstance(auth_user, dict):
        for k in ("user_id", "userid", "name"):
            val = str(auth_user.get(k) or "").strip()
            if val:
                return val
    return _DEFAULT_OWNER_KEY


def resolve_owner_name(session_auth: dict = None) -> str:
    """Resolve the display name from the session auth_user dict."""
    auth_user = session_auth or {}
    if isinstance(auth_user, dict):
        for k in ("name", "nick", "nickname", "user_name"):
            val = str(auth_user.get(k) or "").strip()
            if val:
                return val
    return ""


def user_workspace(owner_key: str) -> dict:
    """Get workspace paths for a given owner_key.

    Returns dict with owner_safe, user_root, claude_dir, workspace_dir, shared_claude_dir.
    """
    safe = safe_owner_key(owner_key)
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


_DEFAULT_WORKSPACE_INIT = None  # resolved lazily to avoid circular import


def _resolve_default_init():
    """Lazy import to avoid circular dependency with ai.tbcreate."""
    global _DEFAULT_WORKSPACE_INIT
    if _DEFAULT_WORKSPACE_INIT is None:
        from ai.tbcreate.workspace import init_workspace as fn
        _DEFAULT_WORKSPACE_INIT = fn
    return _DEFAULT_WORKSPACE_INIT


def write_workspace_context(
    owner_key: str, auth_user: dict = None,
    workspace_init: callable = None,
) -> None:
    """Ensure workspace context files exist before starting a ttyd session.

    Defaults to tbcreate workspace init. Pass a custom init function for
    other ttyd purposes (e.g. knowledge base Q&A).
    """
    init_fn = workspace_init or _resolve_default_init()
    init_fn(owner_key, auth_user)


def make_env(owner_key: str, owner_name: str, model: str) -> dict:
    """Build the environment dict for the ttyd/claude subprocess.

    Sets ANTHROPIC_API_KEY, ANTHROPIC_BASE_URL, ANTHROPIC_MODEL, and user identity vars.
    """
    cfg = load_ai_config()
    api_key = str(cfg.get("api_key") or "").strip()
    base_url = str(cfg.get("base_url") or "").strip()
    if not api_key:
        raise RuntimeError("missing ai/config.json api_key")

    env = os.environ.copy()
    real_home = str(os.environ.get("HOME") or "").strip()
    # Claude Code should use the Anthropic-compatible gateway settings below.
    # Some shells export OpenAI vars globally, and the CLI may prefer them.
    for key in ("OPENAI_API_KEY", "OPENAI_API_BASE", "OPENAI_BASE_URL", "OPENAI_MODEL"):
        env.pop(key, None)
    env["ANTHROPIC_API_KEY"] = api_key
    env["ANTHROPIC_BASE_URL"] = base_url
    env["ANTHROPIC_MODEL"] = model
    # Bypass proxy for the AI gateway (e.g. one-api on 172.19.x)
    try:
        from urllib.parse import urlparse
        api_host = urlparse(base_url).hostname or ""
    except Exception:
        api_host = ""
    if api_host:
        no_proxy = str(env.get("no_proxy") or env.get("NO_PROXY") or "")
        entries = [e.strip() for e in no_proxy.split(",") if e.strip()]
        if api_host not in entries:
            entries.append(api_host)
        env["no_proxy"] = ",".join(entries)
        env["NO_PROXY"] = env["no_proxy"]
    env["AI_OWNER_KEY"] = owner_key
    env["AI_OWNER_NAME"] = owner_name
    env["AI_USERS_ROOT"] = str(_USERS_ROOT)
    env["AI_SHARED_CLAUDE_DIR"] = str(_SHARED_CLAUDE_DIR)
    env["AI_SAFE_OWNER"] = safe_owner_key(owner_key)
    # Flask backend URL for internal curl (e.g. /draft/notify)
    # 优先使用外部显式设置的 AI_FLASK_BASE_URL，再尝试从 FLASK_RUN_PORT 推导
    ai_flask_base_url = str(os.getenv("AI_FLASK_BASE_URL") or "").strip()
    if not ai_flask_base_url:
        flask_port = str(os.getenv("FLASK_RUN_PORT", "5001")).strip() or "5001"
        ai_flask_base_url = f"http://127.0.0.1:{flask_port}"
    env["AI_FLASK_BASE_URL"] = ai_flask_base_url
    # Ensure claude/node binary paths are on PATH
    path_items = [p for p in str(env.get("PATH") or "").split(":") if p]
    preferred_paths = []
    for candidate in (
        f"{real_home}/.nvm/versions/node/v20.20.2/bin" if real_home else "",
        f"{real_home}/.local/bin" if real_home else "",
    ):
        c = str(candidate or "").strip()
        if c:
            preferred_paths.append(c)
    path_items = [p for p in path_items if p not in preferred_paths]
    env["PATH"] = ":".join(preferred_paths + path_items)
    return env


def _session_key(owner_key: str, purpose: str) -> str:
    return f"{owner_key}::{purpose}" if purpose else owner_key


def _normalize_owner_for_port(owner_key: str, purpose: str = "") -> int:
    """Compute a deterministic port offset from an owner_key (+ purpose)."""
    seed = f"{owner_key}::{purpose}".encode("utf-8", errors="ignore")
    return sum(seed) % _DEFAULT_TTYD_PORT_SPAN


def owner_ttyd_port(owner_key: str, purpose: str = "") -> int:
    """Get the preferred ttyd port for an owner_key (stable mapping)."""
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
    return int(base + (_normalize_owner_for_port(owner_key, purpose) % span))


def _is_port_available(host: str, port: int) -> bool:
    """Check if a TCP port is available for binding."""
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


def resolve_ttyd_port(owner_key: str, purpose: str = "") -> int:
    """Find an available ttyd port for an owner_key (+ purpose), preferring stable mapping.

    If the preferred port is occupied, scans forward within the configured span.
    """
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
    preferred = owner_ttyd_port(owner_key, purpose)
    for i in range(span):
        candidate = int(base + ((preferred - base + i) % span))
        if _is_port_available("0.0.0.0", candidate):
            return candidate
    return preferred


def _terminate_ttyd_locked(state: dict, reason: str = "") -> None:
    """Send SIGTERM to a ttyd process group. Must be called under _TTYD_LOCK."""
    proc = state.get("proc")
    if proc is not None and proc.poll() is None:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except Exception:
            pass
    append_log(
        {
            "ts": int(time.time()),
            "phase": "ttyd_session_stop",
            "owner_key": state.get("owner_key", ""),
            "owner_safe": state.get("owner_safe", ""),
            "model": state.get("model", ""),
            "skill": state.get("skill", ""),
            "port": state.get("port", 0),
            "pid": int(proc.pid) if proc is not None else 0,
            "reason": reason,
        }
    )


def _cleanup_ttyd_sessions_locked(now: int = None) -> None:
    """Remove dead or expired ttyd sessions. Must be called under _TTYD_LOCK."""
    current = int(now or time.time())
    ttl = ttyd_ttl_seconds()
    expired_keys = []
    for sk, state in list(_TTYD_SESSIONS.items()):
        proc = state.get("proc")
        if proc is None or proc.poll() is not None:
            expired_keys.append((sk, state, "dead"))
            continue
        created_at = int(state.get("created_at") or 0)
        if created_at and current - created_at >= ttl:
            expired_keys.append((sk, state, "ttl_expired"))
    for sk, state, reason in expired_keys:
        if reason == "ttl_expired":
            _terminate_ttyd_locked(state, reason=reason)
        else:
            append_log(
                {
                    "ts": current,
                    "phase": "ttyd_session_stop",
                    "owner_key": state.get("owner_key", ""),
                    "owner_safe": state.get("owner_safe", ""),
                    "model": state.get("model", ""),
                    "skill": state.get("skill", ""),
                    "port": state.get("port", 0),
                    "pid": int(state.get("proc").pid) if state.get("proc") is not None else 0,
                    "reason": reason,
                }
            )
        _TTYD_SESSIONS.pop(sk, None)


def start_ttyd_janitor() -> None:
    """Start a daemon thread that reaps expired ttyd sessions."""
    global _JANITOR_STARTED
    with _JANITOR_LOCK:
        if _JANITOR_STARTED:
            return
        _JANITOR_STARTED = True

    def _run() -> None:
        while True:
            time.sleep(min(300, max(30, ttyd_ttl_seconds() // 6)))
            with _TTYD_LOCK:
                _cleanup_ttyd_sessions_locked()

    thread = threading.Thread(target=_run, name="ttyd-session-janitor", daemon=True)
    thread.start()


def build_ttyd_embed_url(port: int, owner_key: str, model: str, skill: str = "") -> str:
    """Build the iframe embed URL for a ttyd session.

    Uses AI_TTYD_BASE_URL env var template, falling back to http://127.0.0.1:{port}/.
    """
    tpl = str(os.getenv("AI_TTYD_BASE_URL") or "").strip()
    if not tpl:
        tpl = "http://127.0.0.1:{port}/"
    tpl = tpl.replace("{port/}", "{port}/")
    if "{port}" in tpl:
        url = tpl.replace("{port}", str(port))
    else:
        url = tpl
    joiner = "&" if "?" in url else "?"
    parts = [f"{joiner}ownerKey={owner_key}&model={model}"]
    skill_trigger = str(skill or "").strip()
    if skill_trigger:
        parts.append(f"&skill={skill_trigger}")
    return url + "".join(parts)


def ensure_ttyd_session(
    owner_key: str, owner_name: str, model: str, auth_user: dict = None, skill: str = "",
    workspace_init: callable = None, purpose: str = "",
) -> dict:
    """Create or reuse a ttyd + claude session for the given owner_key.

    If an existing session with the same owner_key + purpose is alive, returns it.
    Otherwise terminates any stale session, allocates a port, launches
    ttyd -> launcher.sh -> claude, and returns the new session state.

    Args:
        owner_key: Unique user identifier for session isolation.
        owner_name: Display name for the session.
        model: AI model name to pass to the launcher.
        auth_user: Optional authenticated user dict for workspace context.
        skill: Skill trigger phrase (e.g. "创建tb单"). Passed as initial prompt to Claude.
        workspace_init: Optional workspace init function (owner_key, auth_user) -> dict.
                       Defaults to tbcreate workspace init.
        purpose: Session purpose tag (e.g. "knowledge"). Different purposes get
                 separate ports and processes for the same owner_key.

    Returns:
        Dict with owner_key, purpose, owner_safe, model, port, proc, created_at.

    Raises:
        RuntimeError: If ttyd is not installed or fails to start.
    """
    start_ttyd_janitor()
    sk = _session_key(owner_key, purpose)
    with _TTYD_LOCK:
        _cleanup_ttyd_sessions_locked()
        skill_trigger = str(skill or "").strip()
        existing = _TTYD_SESSIONS.get(sk)
        if existing:
            if existing["proc"].poll() is None:
                if existing.get("model") == model and existing.get("skill") == skill_trigger:
                    return existing
                _terminate_ttyd_locked(existing, reason="model_or_skill_changed")
            else:
                _terminate_ttyd_locked(existing, reason="stale")
            _TTYD_SESSIONS.pop(sk, None)

        resolved_env = make_env(owner_key=owner_key, owner_name=owner_name, model=model)
        write_workspace_context(owner_key, auth_user or {}, workspace_init=workspace_init)
        port = resolve_ttyd_port(owner_key, purpose)
        cmd = [
            "ttyd",
            "-W",
            "-i",
            "0.0.0.0",
            "-p",
            str(port),
            "bash",
            str(_EASY_START_JZ_SCRIPT),
        ]
        if skill_trigger:
            cmd.append(skill_trigger)
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

        ws = user_workspace(owner_key)
        state = {
            "owner_key": owner_key,
            "purpose": purpose,
            "owner_safe": ws["owner_safe"],
            "model": model,
            "skill": skill_trigger,
            "port": port,
            "proc": proc,
            "created_at": int(time.time()),
            "expires_at": int(time.time()) + ttyd_ttl_seconds(),
        }
        _TTYD_SESSIONS[sk] = state
        append_log(
            {
                "ts": int(time.time()),
                "phase": "ttyd_session_start",
                "owner_key": owner_key,
                "owner_safe": ws["owner_safe"],
                "model": model,
                "skill": skill_trigger,
                "port": port,
                "pid": proc.pid,
            }
        )
        return state
