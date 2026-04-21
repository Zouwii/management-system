"""AI interactive routes (compat + /ai/interactive/*)."""

import json
import os
import pty
import re
import select
import signal
import subprocess
import threading
import time
from pathlib import Path

from flask import request

_AI_CONFIG_PATH = Path(__file__).resolve().parent.parent / "ai" / "config.json"
_START_SCRIPT = Path(__file__).resolve().parent.parent / "ai" / "start_claude_interactive.py"
_RUNTIME_DIR = Path(__file__).resolve().parent.parent / "runtime"
_CLAUDE_HOME = _RUNTIME_DIR / "claude-home"
_LOG_FILE = _RUNTIME_DIR / "logs" / "ai_debug_subprocess.log"
_ANSI_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
_CURSOR_RIGHT_RE = re.compile(r"\x1b\[(\d*)C")
_ESC_SIMPLE_RE = re.compile(r"\x1b[0-9=><]")
_OSC_RE = re.compile(r"\x1b\].*?(?:\x07|\x1b\\)", re.DOTALL)
_SPINNER_ONLY_RE = re.compile(r"^[\s\-\.\*\u2736\u2722\u273b\u273d\u2800-\u28ff]+$")
_DEFAULT_TIMEOUT_SECONDS = 15
_DEFAULT_OWNER_KEY = "anonymous"
_SESSIONS = {}
_SESSION_LOCK = threading.Lock()


def _ensure_dirs() -> None:
    (_RUNTIME_DIR / "logs").mkdir(parents=True, exist_ok=True)
    _CLAUDE_HOME.mkdir(parents=True, exist_ok=True)


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


def _strip_ansi(text: str) -> str:
    source = str(text or "")
    source = _OSC_RE.sub("", source)
    # 把 ANSI 的光标右移转换为空格，避免 "Welcome to" 变成 "Welcometo"
    source = _CURSOR_RIGHT_RE.sub(lambda m: " " * max(int(m.group(1) or "1"), 1), source)
    source = _ESC_SIMPLE_RE.sub("", source)
    return _ANSI_RE.sub("", source).replace("\r", "").strip()


def _filter_terminal_noise(text: str) -> str:
    lines = [ln.rstrip() for ln in str(text or "").splitlines()]
    kept = []
    for line in lines:
        s = line.strip()
        if not s:
            if kept and kept[-1] != "":
                kept.append("")
            continue
        low = s.lower()
        if "hashing" in low:
            continue
        if "herding" in low:
            continue
        if "esc to interrupt" in low:
            continue
        if "failed to install anthropic marketplace" in low:
            continue
        if _SPINNER_ONLY_RE.match(s):
            continue
        if "claude code" in low and any(ch in s for ch in ("⠂", "⠐", "✶", "✢", "✻", "✽")):
            continue
        kept.append(s)
    while kept and kept[-1] == "":
        kept.pop()
    return "\n".join(kept).strip()


def _extract_zhr_block(text: str) -> str:
    # 只接受“标记独占一行”的格式，避免匹配到解释性句子：
    # 例如“以 #zhr_start 开头，以 #zhr_end 为结尾”
    lines = [ln.strip() for ln in str(text or "").splitlines()]
    blocks = []
    collecting = False
    buf = []
    for ln in lines:
        low = ln.lower()
        if low in ("#zhr_start", "#zhr_begin"):
            collecting = True
            buf = []
            continue
        if collecting and low == "#zhr_end":
            blocks.append("\n".join(buf))
            collecting = False
            buf = []
            continue
        if collecting:
            buf.append(ln)
    if not blocks:
        return ""
    body = blocks[-1]
    body_lines = [ln.strip() for ln in str(body or "").splitlines()]
    # 过滤掉块内常见终端状态噪声
    cleaned = []
    for ln in body_lines:
        if not ln:
            continue
        low = ln.lower()
        if "thinking" in low or "tokens" in low:
            continue
        if _SPINNER_ONLY_RE.match(ln):
            continue
        cleaned.append(ln)
    return "\n".join(cleaned).strip()


def _make_env() -> dict:
    cfg = _load_ai_config()
    model = str(cfg.get("model") or "glm-5.1").strip() or "glm-5.1"
    api_key = str(cfg.get("api_key") or "").strip()
    base_url = str(cfg.get("base_url") or "").strip()
    if not api_key:
        raise RuntimeError("missing ai/config.json api_key")

    env = os.environ.copy()
    env["ANTHROPIC_API_KEY"] = api_key
    env["ANTHROPIC_BASE_URL"] = base_url
    env["ANTHROPIC_MODEL"] = model
    env["HOME"] = str(_CLAUDE_HOME)
    return {"env": env, "model": model, "base_url": base_url}

def _read_pty_output(master_fd: int, wait_seconds: float, idle_break_seconds: float) -> str:
    chunks = []
    started = time.time()
    last_data_at = None
    while True:
        now = time.time()
        if (now - started) >= wait_seconds:
            break
        timeout = min(0.2, max(0.05, wait_seconds - (now - started)))
        ready, _, _ = select.select([master_fd], [], [], timeout)
        if not ready:
            if last_data_at and (time.time() - last_data_at) >= idle_break_seconds:
                break
            continue
        try:
            data = os.read(master_fd, 4096)
        except OSError:
            break
        if not data:
            break
        chunks.append(data)
        last_data_at = time.time()
    return b"".join(chunks).decode("utf-8", errors="replace")


def _terminate_session_locked(session: dict) -> None:
    proc = session.get("proc")
    master_fd = session.get("master_fd")
    if proc is not None and proc.poll() is None:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except Exception:
            pass
    if master_fd is not None:
        try:
            os.close(master_fd)
        except Exception:
            pass


def _normalize_owner_key(payload: dict) -> str:
    key = str((payload or {}).get("ownerKey") or "").strip()
    return key or _DEFAULT_OWNER_KEY


def _ensure_session(owner_key: str, startup_timeout: int) -> dict:
    with _SESSION_LOCK:
        existing = _SESSIONS.get(owner_key)
        if existing and existing["proc"].poll() is None:
            return existing
        if existing:
            _terminate_session_locked(existing)
            _SESSIONS.pop(owner_key, None)

        resolved = _make_env()
        cmd = ["python3", str(_START_SCRIPT)]
        master_fd, slave_fd = pty.openpty()
        try:
            proc = subprocess.Popen(
                cmd,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                env=resolved["env"],
                text=False,
                start_new_session=True,
            )
        finally:
            try:
                os.close(slave_fd)
            except Exception:
                pass
        session = {
            "owner_key": owner_key,
            "proc": proc,
            "master_fd": master_fd,
            "model": resolved["model"],
            "base_url": resolved["base_url"],
            "lock": threading.Lock(),
            "created_at": int(time.time()),
        }
        _SESSIONS[owner_key] = session
        _append_log(
            {
                "ts": int(time.time()),
                "phase": "session_start",
                "owner_key": owner_key,
                "pid": proc.pid,
                "cmd": cmd,
                "model": resolved["model"],
                "base_url": resolved["base_url"],
            }
        )
    # 在会话锁外读欢迎内容，避免阻塞其他会话管理
    with session["lock"]:
        startup_raw = _read_pty_output(
            session["master_fd"],
            wait_seconds=max(float(startup_timeout), 3.0),
            idle_break_seconds=0.8,
        )
        # 首次启动会出现主题选择向导，这里自动选择 Dark mode，避免阻塞后续交互。
        if "Choose the text style" in startup_raw:
            try:
                os.write(session["master_fd"], b"2\n")
            except OSError:
                pass
            startup_raw += _read_pty_output(
                session["master_fd"],
                wait_seconds=2.0,
                idle_break_seconds=0.6,
            )
    session["startup_raw"] = startup_raw
    return session


def _session_response(text: str, raw: str, session: dict) -> dict:
    return {
        "result": {"type": "result", "data": {"result": text}},
        "debug": {
            "model": session.get("model"),
            "base_url": session.get("base_url"),
            "log_file": str(_LOG_FILE),
            "raw_terminal_output": raw[:4000],
        },
    }


def register(bp, ok, fail):
    def _handle_models():
        cfg = _load_ai_config()
        model = str(cfg.get("model") or "glm-5.1").strip() or "glm-5.1"
        return ok({"models": [{"name": model, "description": "default model"}]})

    def _handle_session_message():
        payload = request.get_json(silent=True) or {}
        owner_key = _normalize_owner_key(payload)
        prompt = str(payload.get("prompt") or payload.get("content") or "").strip()
        if not prompt:
            return fail("prompt is required", code=400, data={})
        timeout_seconds = max(int(payload.get("timeoutSeconds") or payload.get("timeout") or _DEFAULT_TIMEOUT_SECONDS), 3)
        try:
            session = _ensure_session(owner_key=owner_key, startup_timeout=3)
        except Exception as exc:
            return fail(str(exc), code=500, data={})

        with session["lock"]:
            proc = session["proc"]
            if proc.poll() is not None:
                return fail("claude session exited unexpectedly", code=500, data={})
            try:
                # TTY 交互下多数程序以 CR(\r) 作为 Enter，避免仅 LF(\n) 导致输入不提交。
                payload_bytes = (prompt + "\r").encode("utf-8", errors="replace")
                written = os.write(session["master_fd"], payload_bytes)
                _append_log(
                    {
                        "ts": int(time.time()),
                        "phase": "session_write_ok",
                        "owner_key": owner_key,
                        "prompt_len": len(prompt),
                        "bytes_to_write": len(payload_bytes),
                        "bytes_written": int(written),
                    }
                )
                _append_log(
                    {
                        "ts": int(time.time()),
                        "phase": "session_proc_poll_after_write",
                        "owner_key": owner_key,
                        "proc_alive": proc.poll() is None,
                        "proc_returncode": proc.returncode,
                    }
                )
            except OSError as exc:
                return fail(f"write prompt failed: {exc}", code=500, data={})
            raw = _read_pty_output(
                session["master_fd"],
                wait_seconds=float(timeout_seconds),
                idle_break_seconds=1.1,
            )
        clean = _strip_ansi(raw)
        tagged = _extract_zhr_block(clean)
        display = tagged or _filter_terminal_noise(clean)
        _append_log(
            {
                "ts": int(time.time()),
                "phase": "session_message",
                "owner_key": owner_key,
                "prompt_len": len(prompt),
                "output_len": len(raw),
                "zhr_block_hit": bool(tagged),
                "output_preview": display[:600],
            }
        )
        if not raw:
            return fail("no output after prompt", code=500, data={})
        return ok(_session_response(display or clean or raw, raw, session))

    def _handle_session_start():
        payload = request.get_json(silent=True) or {}
        owner_key = _normalize_owner_key(payload)
        timeout_seconds = max(int(payload.get("timeoutSeconds") or payload.get("timeout") or 8), 3)
        try:
            session = _ensure_session(owner_key=owner_key, startup_timeout=timeout_seconds)
        except Exception as exc:
            return fail(str(exc), code=500, data={})
        raw = str(session.get("startup_raw") or "")
        clean = _strip_ansi(raw)
        tagged = _extract_zhr_block(clean)
        display = tagged or _filter_terminal_noise(clean)
        return ok(_session_response(display or clean or raw, raw, session))

    def _handle_session_end():
        payload = request.get_json(silent=True) or {}
        owner_key = _normalize_owner_key(payload)
        with _SESSION_LOCK:
            session = _SESSIONS.pop(owner_key, None)
        if session:
            with session["lock"]:
                _terminate_session_locked(session)
            _append_log(
                {
                    "ts": int(time.time()),
                    "phase": "session_end",
                    "owner_key": owner_key,
                }
            )
        return ok({"ended": True, "ownerKey": owner_key})

    @bp.route("/ai/models", methods=["GET"])
    def ai_models():
        return _handle_models()

    @bp.route("/ai/interactive/models", methods=["GET"])
    def ai_interactive_models():
        return _handle_models()

    @bp.route("/ai/chat/session_message", methods=["POST"])
    def ai_chat_session_message():
        return _handle_session_message()

    @bp.route("/ai/interactive/message", methods=["POST"])
    def ai_interactive_message():
        return _handle_session_message()

    @bp.route("/ai/chat/session_start", methods=["POST"])
    def ai_chat_session_start():
        return _handle_session_start()

    @bp.route("/ai/interactive/start", methods=["POST"])
    def ai_interactive_start():
        return _handle_session_start()

    @bp.route("/ai/chat/session_message_stream", methods=["POST"])
    def ai_chat_session_message_stream():
        return fail("not implemented", code=501, data={})

    @bp.route("/ai/chat/session_end", methods=["POST"])
    def ai_chat_session_end():
        return _handle_session_end()

    @bp.route("/ai/interactive/end", methods=["POST"])
    def ai_interactive_end():
        return _handle_session_end()

