"""AI ttyd session routes."""

import json
import os
import hashlib
import signal
import subprocess
import threading
import time
import socket
from datetime import datetime
from pathlib import Path

from flask import request, session

_AI_CONFIG_PATH = Path(__file__).resolve().parent.parent / "ai" / "config.json"
_EASY_START_JZ_SCRIPT = Path(__file__).resolve().parent.parent / "easy_start_claude_jz"
_RUNTIME_DIR = Path(__file__).resolve().parent.parent / "runtime"
_CLAUDE_HOME = _RUNTIME_DIR / "claude-home"
_LOG_FILE = _RUNTIME_DIR / "logs" / "ai_debug_subprocess.log"
_AI_CACHE_SPACES_DIR = Path(__file__).resolve().parent.parent / "ai" / "cache" / "spaces"
_DEFAULT_OWNER_KEY = "anonymous"
_DEFAULT_TTYD_PORT_BASE = 8800
_DEFAULT_TTYD_PORT_SPAN = 400
_TTYD_SESSIONS = {}
_TTYD_LOCK = threading.Lock()


def _ensure_dirs() -> None:
    (_RUNTIME_DIR / "logs").mkdir(parents=True, exist_ok=True)
    _CLAUDE_HOME.mkdir(parents=True, exist_ok=True)
    _AI_CACHE_SPACES_DIR.mkdir(parents=True, exist_ok=True)


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


def _make_env() -> dict:
    cfg = _load_ai_config()
    model = str(cfg.get("model") or "glm-5.1").strip() or "glm-5.1"
    api_key = str(cfg.get("api_key") or "").strip()
    base_url = str(cfg.get("base_url") or "").strip()
    if not api_key:
        raise RuntimeError("missing ai/config.json api_key")

    env = os.environ.copy()
    real_home = str(os.environ.get("HOME") or "").strip()
    env["ANTHROPIC_API_KEY"] = api_key
    env["ANTHROPIC_BASE_URL"] = base_url
    env["ANTHROPIC_MODEL"] = model
    env["HOME"] = str(_CLAUDE_HOME)
    # 某些启动链路下 PATH 不含 nvm / local bin，导致找不到 claude。
    path_items = [p for p in str(env.get("PATH") or "").split(":") if p]
    for candidate in (
        f"{real_home}/.nvm/versions/node/v20.20.2/bin" if real_home else "",
        f"{real_home}/.local/bin" if real_home else "",
    ):
        c = str(candidate or "").strip()
        if c and c not in path_items:
            path_items.append(c)
    env["PATH"] = ":".join(path_items)
    return {"env": env, "model": model, "base_url": base_url}


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


def _safe_owner_key(owner_key: str) -> str:
    raw = str(owner_key or "").strip() or _DEFAULT_OWNER_KEY
    return hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()[:24]


def _ensure_owner_cache_binding(owner_key: str) -> dict:
    from sqlalchemy.exc import IntegrityError

    from db.engine import SessionLocal
    from db.orm import AiCacheSpace, AiUserCacheMap

    safe_owner = _safe_owner_key(owner_key)
    cache_id = f"cache_{safe_owner}"
    cache_dir = _AI_CACHE_SPACES_DIR / cache_id
    cache_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    db = SessionLocal()
    try:
        mapping = db.query(AiUserCacheMap).filter(AiUserCacheMap.owner_key == owner_key).first()
        if not mapping:
            mapping = AiUserCacheMap(
                owner_key=owner_key,
                cache_id=cache_id,
                status=1,
                created_at=now,
                updated_at=now,
            )
            db.add(mapping)
            try:
                db.flush()
            except IntegrityError:
                db.rollback()
                mapping = db.query(AiUserCacheMap).filter(AiUserCacheMap.owner_key == owner_key).first()
        if mapping:
            cache_id = str(mapping.cache_id or cache_id)
            mapping.updated_at = now
        space = db.query(AiCacheSpace).filter(AiCacheSpace.cache_id == cache_id).first()
        if not space:
            space = AiCacheSpace(
                cache_id=cache_id,
                cache_dir=str(_AI_CACHE_SPACES_DIR / cache_id),
                created_at=now,
                updated_at=now,
                last_access_at=now,
            )
            db.add(space)
        else:
            space.updated_at = now
            space.last_access_at = now
        db.commit()
        resolved_dir = Path(str(space.cache_dir))
        resolved_dir.mkdir(parents=True, exist_ok=True)
        return {"cache_id": cache_id, "cache_dir": str(resolved_dir)}
    finally:
        db.close()


def _touch_cache_space(cache_id: str, *, pid: int | None = None, port: int | None = None, model: str | None = None) -> None:
    from db.engine import SessionLocal
    from db.orm import AiCacheSpace

    now = datetime.now()
    db = SessionLocal()
    try:
        space = db.query(AiCacheSpace).filter(AiCacheSpace.cache_id == cache_id).first()
        if not space:
            return
        if pid is not None:
            space.active_pid = int(pid)
        if port is not None:
            space.active_port = int(port)
        if model is not None:
            space.model = str(model)
        space.last_access_at = now
        space.updated_at = now
        db.commit()
    finally:
        db.close()


def _mark_cache_space_stopped(cache_id: str) -> None:
    from db.engine import SessionLocal
    from db.orm import AiCacheSpace

    now = datetime.now()
    db = SessionLocal()
    try:
        space = db.query(AiCacheSpace).filter(AiCacheSpace.cache_id == cache_id).first()
        if not space:
            return
        space.active_pid = None
        space.active_port = None
        space.updated_at = now
        space.last_access_at = now
        db.commit()
    finally:
        db.close()


def _normalize_owner_for_port(owner_key: str) -> int:
    seed = owner_key.encode("utf-8", errors="ignore")
    # 稳定映射：同一 ownerKey 固定端口。
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
    # 兼容历史误配："{port/}" 也按 "{port}/" 处理。
    tpl = tpl.replace("{port/}", "{port}/")
    if "{port}" in tpl:
        url = tpl.replace("{port}", str(port))
    else:
        url = tpl
    joiner = "&" if "?" in url else "?"
    return f"{url}{joiner}ownerKey={owner_key}&model={model}"


def _ensure_ttyd_session(owner_key: str, model: str) -> dict:
    with _TTYD_LOCK:
        existing = _TTYD_SESSIONS.get(owner_key)
        if existing and existing["proc"].poll() is None:
            cache_id = str(existing.get("cache_id") or "")
            if cache_id:
                try:
                    _touch_cache_space(cache_id, pid=existing["proc"].pid, port=existing.get("port"), model=model)
                except Exception:
                    pass
            return existing
        if existing:
            _terminate_ttyd_locked(existing)
            old_cache_id = str(existing.get("cache_id") or "")
            if old_cache_id:
                try:
                    _mark_cache_space_stopped(old_cache_id)
                except Exception:
                    pass
            _TTYD_SESSIONS.pop(owner_key, None)

        resolved = _make_env()
        resolved_env = dict(resolved["env"])
        resolved_env["ANTHROPIC_MODEL"] = model
        cache_binding = _ensure_owner_cache_binding(owner_key)
        cache_id = str(cache_binding.get("cache_id") or "")
        cache_dir = str(cache_binding.get("cache_dir") or "")
        resolved_env["AI_OWNER_KEY"] = owner_key
        resolved_env["AI_CACHE_ID"] = cache_id
        resolved_env["AI_CACHE_DIR"] = cache_dir
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

        state = {
            "owner_key": owner_key,
            "cache_id": cache_id,
            "cache_dir": cache_dir,
            "model": model,
            "port": port,
            "proc": proc,
            "created_at": int(time.time()),
        }
        _TTYD_SESSIONS[owner_key] = state
        try:
            _touch_cache_space(cache_id, pid=proc.pid, port=port, model=model)
        except Exception:
            pass
        _append_log(
            {
                "ts": int(time.time()),
                "phase": "ttyd_session_start",
                "owner_key": owner_key,
                "cache_id": cache_id,
                "model": model,
                "port": port,
                "pid": proc.pid,
                "cmd": cmd,
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
                cache_id = str(ttyd_state.get("cache_id") or "")
                if cache_id:
                    try:
                        _mark_cache_space_stopped(cache_id)
                    except Exception:
                        pass
                _append_log(
                    {
                        "ts": int(time.time()),
                        "phase": "ttyd_session_end",
                        "owner_key": owner_key,
                        "cache_id": ttyd_state.get("cache_id"),
                        "port": ttyd_state.get("port"),
                    }
                )
        return ok({"ended": True, "ownerKey": owner_key})

    def _handle_ttyd_session():
        payload = request.get_json(silent=True) or {}
        owner_key = _resolve_owner_key(payload)
        cfg = _load_ai_config()
        model = str(payload.get("model") or cfg.get("model") or "glm-5.1").strip() or "glm-5.1"
        try:
            state = _ensure_ttyd_session(owner_key=owner_key, model=model)
        except Exception as exc:
            return fail(str(exc), code=500, data={})
        embed_url = _build_ttyd_embed_url(
            port=int(state.get("port") or _owner_ttyd_port(owner_key)),
            owner_key=owner_key,
            model=model,
        )
        return ok(
            {
                "embedUrl": embed_url,
                "ownerKey": owner_key,
                "cacheId": str(state.get("cache_id") or ""),
                "model": model,
                "port": int(state.get("port") or 0),
                "pid": int(state.get("proc").pid) if state.get("proc") else 0,
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

