import json
import socket
import threading
import time
from typing import Any, Dict, List
from urllib.parse import urlparse

import requests

from services.ai_token_service import get_valid_ai_token_service

_DEFAULT_API_BASE = "http://claude.server22.jz"
_CHAT_SESSIONS: Dict[str, Dict[str, Any]] = {}
_CHAT_SESSIONS_LOCK = threading.Lock()
_SESSION_IDLE_TIMEOUT_SECONDS = 600


def _load_ai_server_config() -> Dict[str, Any]:
    from dingtalk_client import _load_config_json  # 复用现有配置读取

    cfg = _load_config_json()
    token_api = str(cfg.get("ai_token_api") or f"{_DEFAULT_API_BASE}/api/v1/token").strip()
    parsed = urlparse(token_api)
    host = parsed.hostname or "claude.server22.jz"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return {
        "host": host,
        "port": int(port),
        "scheme": parsed.scheme or "http",
        "base_url": f"{parsed.scheme or 'http'}://{host}{':' + str(port) if parsed.port else ''}",
    }


def _send(sock: socket.socket, msg: Dict[str, Any]) -> None:
    sock.sendall((json.dumps(msg, ensure_ascii=False) + "\n").encode())


def _recv_json_line(sock: socket.socket, timeout: int = 30) -> Dict[str, Any]:
    buf = b""
    sock.settimeout(timeout)
    while b"\n" not in buf:
        chunk = sock.recv(4096)
        if not chunk:
            raise RuntimeError("socket closed by peer before receiving json line")
        buf += chunk
    line = buf.split(b"\n", 1)[0].strip()
    return json.loads(line.decode("utf-8", errors="replace"))


def _cleanup_idle_sessions(now_ts: float) -> None:
    stale_items = []
    with _CHAT_SESSIONS_LOCK:
        for conv_id, session in list(_CHAT_SESSIONS.items()):
            last_active = float(session.get("last_active_at") or session.get("created_at") or 0.0)
            if last_active <= 0:
                continue
            if now_ts - last_active >= _SESSION_IDLE_TIMEOUT_SECONDS:
                stale_items.append((conv_id, _CHAT_SESSIONS.pop(conv_id)))

    for conv_id, session in stale_items:
        sock = session.get("sock")
        if sock:
            try:
                _send(sock, {"type": "end"})
                _recv_json_line(sock, timeout=2)
            except Exception:
                pass
            finally:
                try:
                    sock.close()
                except Exception:
                    pass
        print(
            f"[ai_session] cleanup idle conversation_id={conv_id} "
            f"idle_timeout_s={_SESSION_IDLE_TIMEOUT_SECONDS}"
        )


def _open_ws_and_start(model: str, timeout_seconds: int) -> Dict[str, Any]:
    token_out = get_valid_ai_token_service()
    if not token_out.get("success"):
        return {"success": False, "error": token_out.get("error", "failed to get valid ai token")}
    token = str(token_out.get("token") or "").strip()
    if not token:
        return {"success": False, "error": "missing token"}

    server = _load_ai_server_config()
    host = server["host"]
    port = server["port"]

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout_seconds)
    sock.connect((host, port))
    sock.sendall(
        (
            f"GET /api/v1/session?token={token} HTTP/1.1\r\n"
            f"Host: {host}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n\r\n"
        ).encode()
    )

    resp = b""
    while b"\r\n\r\n" not in resp:
        chunk = sock.recv(4096)
        if not chunk:
            break
        resp += chunk
    if b" 101 " not in resp:
        sock.close()
        return {"success": False, "error": f"websocket handshake failed: {resp.decode(errors='replace')}"}

    _send(sock, {"type": "start", "model": model})
    started = _recv_json_line(sock, timeout=timeout_seconds)
    if str(started.get("type") or "") != "started":
        sock.close()
        return {"success": False, "error": f"start session failed: {started}"}

    return {
        "success": True,
        "sock": sock,
        "server": {"host": host, "port": port},
        "started": started,
    }


def get_ai_models_service(timeout_seconds: int = 15) -> Dict[str, Any]:
    token_out = get_valid_ai_token_service()
    if not token_out.get("success"):
        return {"success": False, "error": token_out.get("error", "failed to get valid ai token")}
    token = str(token_out.get("token") or "").strip()
    if not token:
        return {"success": False, "error": "missing token"}

    server = _load_ai_server_config()
    models_url = f"{server['base_url']}/api/v1/models"
    try:
        resp = requests.get(
            models_url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=max(int(timeout_seconds or 15), 3),
        )
        data = resp.json()
    except Exception as e:
        return {"success": False, "error": str(e), "models_url": models_url}

    models = data.get("models")
    if resp.status_code != 200 or not isinstance(models, list):
        return {
            "success": False,
            "error": str(data.get("error") or "failed to fetch models"),
            "http_status": resp.status_code,
            "models_url": models_url,
            "response": data,
        }
    return {
        "success": True,
        "models": models,
        "models_url": models_url,
        "http_status": resp.status_code,
    }


def send_session_message_service(
    conversation_id: str,
    prompt: str,
    model: str = "glm",
    timeout_seconds: int = 45,
) -> Dict[str, Any]:
    conv_id = str(conversation_id or "").strip()
    content = str(prompt or "").strip()
    if not conv_id:
        return {"success": False, "error": "conversation_id is required"}
    if not content:
        return {"success": False, "error": "prompt is required"}

    timeout_seconds = max(int(timeout_seconds or 45), 5)
    started_at = time.time()
    _cleanup_idle_sessions(started_at)

    def _try_send_once(sess: Dict[str, Any]) -> Dict[str, Any]:
        sock = sess["sock"]
        round_started_at = time.time()
        _send(sock, {"type": "prompt", "content": content})
        result = _recv_json_line(sock, timeout=timeout_seconds)
        sess["last_active_at"] = time.time()
        total_ms_local = int((time.time() - started_at) * 1000)
        round_ms_local = int((time.time() - round_started_at) * 1000)
        print(
            f"[ai_session] message conversation_id={conv_id} cost_ms={round_ms_local} total_ms={total_ms_local}"
        )
        return {
            "success": True,
            "conversation_id": conv_id,
            "result": result,
            "timing": {
                "message_ms": round_ms_local,
                "total_ms": total_ms_local,
            },
        }

    try:
        with _CHAT_SESSIONS_LOCK:
            session = _CHAT_SESSIONS.get(conv_id)

        if not session:
            create_started_at = time.time()
            created = _open_ws_and_start(model=model, timeout_seconds=timeout_seconds)
            if not created.get("success"):
                return created
            session = {
                "sock": created["sock"],
                "server": created["server"],
                "started": created["started"],
                "model": model,
                "created_at": time.time(),
                "last_active_at": time.time(),
            }
            with _CHAT_SESSIONS_LOCK:
                _CHAT_SESSIONS[conv_id] = session
            print(
                f"[ai_session] create conversation_id={conv_id} model={model} "
                f"cost_ms={int((time.time() - create_started_at) * 1000)}"
            )

        try:
            return _try_send_once(session)
        except Exception as first_err:
            err_text = str(first_err)
            should_retry = any(
                k in err_text.lower()
                for k in [
                    "socket closed",
                    "broken pipe",
                    "connection reset",
                    "timed out",
                ]
            )
            if not should_retry:
                raise

            print(
                f"[ai_session] stale socket conversation_id={conv_id}, recreate and retry once, error={first_err}"
            )
            with _CHAT_SESSIONS_LOCK:
                old = _CHAT_SESSIONS.pop(conv_id, None)
            if old and old.get("sock"):
                try:
                    old["sock"].close()
                except Exception:
                    pass

            recreated = _open_ws_and_start(model=model, timeout_seconds=timeout_seconds)
            if not recreated.get("success"):
                return recreated
            session = {
                "sock": recreated["sock"],
                "server": recreated["server"],
                "started": recreated["started"],
                "model": model,
                "created_at": time.time(),
                "last_active_at": time.time(),
            }
            with _CHAT_SESSIONS_LOCK:
                _CHAT_SESSIONS[conv_id] = session
            print(f"[ai_session] recreate conversation_id={conv_id} retry=1")
            return _try_send_once(session)
    except Exception as e:
        with _CHAT_SESSIONS_LOCK:
            bad = _CHAT_SESSIONS.pop(conv_id, None)
        if bad and bad.get("sock"):
            try:
                bad["sock"].close()
            except Exception:
                pass
        return {"success": False, "error": str(e), "conversation_id": conv_id}


def end_session_service(conversation_id: str, timeout_seconds: int = 10) -> Dict[str, Any]:
    conv_id = str(conversation_id or "").strip()
    if not conv_id:
        return {"success": False, "error": "conversation_id is required"}

    with _CHAT_SESSIONS_LOCK:
        session = _CHAT_SESSIONS.pop(conv_id, None)
    if not session:
        return {"success": True, "conversation_id": conv_id, "ended": False, "message": "session not found"}

    sock = session.get("sock")
    if not sock:
        return {"success": True, "conversation_id": conv_id, "ended": False, "message": "socket missing"}

    try:
        _send(sock, {"type": "end"})
        ended = _recv_json_line(sock, timeout=max(int(timeout_seconds or 10), 1))
    except Exception:
        ended = {"type": "ended", "session_id": None}
    finally:
        try:
            sock.close()
        except Exception:
            pass
    return {"success": True, "conversation_id": conv_id, "ended": True, "result": ended}


def run_multi_turn_chat_service(prompts: List[str], model: str = "glm", timeout_seconds: int = 30) -> Dict[str, Any]:
    started_at = time.time()
    prompt_list = [str(x).strip() for x in (prompts or []) if str(x).strip()]
    if not prompt_list:
        return {"success": False, "error": "prompts is empty"}

    token_out = get_valid_ai_token_service()
    if not token_out.get("success"):
        return {"success": False, "error": token_out.get("error", "failed to get valid ai token")}
    token = str(token_out.get("token") or "").strip()
    if not token:
        return {"success": False, "error": "missing token"}

    server = _load_ai_server_config()
    host = server["host"]
    port = server["port"]

    timeout_seconds = max(int(timeout_seconds or 30), 5)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        print(
            f"[ai_multi_turn] begin model={model} rounds={len(prompt_list)} timeout={timeout_seconds}s"
        )
        sock.settimeout(timeout_seconds)
        connect_started_at = time.time()
        sock.connect((host, port))
        print(
            f"[ai_multi_turn] connected host={host} port={port} "
            f"cost_ms={int((time.time() - connect_started_at) * 1000)}"
        )
        sock.sendall(
            (
                f"GET /api/v1/session?token={token} HTTP/1.1\r\n"
                f"Host: {host}\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n\r\n"
            ).encode()
        )

        resp = b""
        handshake_started_at = time.time()
        while b"\r\n\r\n" not in resp:
            chunk = sock.recv(4096)
            if not chunk:
                break
            resp += chunk
        print(
            f"[ai_multi_turn] handshake cost_ms={int((time.time() - handshake_started_at) * 1000)}"
        )
        if b" 101 " not in resp:
            return {
                "success": False,
                "error": f"websocket handshake failed: {resp.decode(errors='replace')}",
            }

        _send(sock, {"type": "start", "model": model})
        start_rsp_started_at = time.time()
        started = _recv_json_line(sock, timeout=timeout_seconds)
        print(
            f"[ai_multi_turn] start_ack type={started.get('type')} "
            f"cost_ms={int((time.time() - start_rsp_started_at) * 1000)}"
        )

        rounds: List[Dict[str, Any]] = []
        for idx, content in enumerate(prompt_list):
            round_started_at = time.time()
            _send(sock, {"type": "prompt", "content": content})
            result = _recv_json_line(sock, timeout=timeout_seconds)
            print(
                f"[ai_multi_turn] round={idx + 1}/{len(prompt_list)} "
                f"cost_ms={int((time.time() - round_started_at) * 1000)}"
            )
            rounds.append(
                {
                    "round": idx + 1,
                    "prompt": content,
                    "response": result,
                }
            )

        _send(sock, {"type": "end"})
        end_rsp_started_at = time.time()
        ended = _recv_json_line(sock, timeout=timeout_seconds)
        print(
            f"[ai_multi_turn] end_ack type={ended.get('type')} "
            f"cost_ms={int((time.time() - end_rsp_started_at) * 1000)}"
        )
        total_ms = int((time.time() - started_at) * 1000)
        print(f"[ai_multi_turn] done total_ms={total_ms}")

        return {
            "success": True,
            "server": {"host": host, "port": port},
            "started": started,
            "rounds": rounds,
            "ended": ended,
            "timing": {
                "total_ms": total_ms,
            },
        }
    except Exception as e:
        total_ms = int((time.time() - started_at) * 1000)
        print(f"[ai_multi_turn] failed total_ms={total_ms} error={e}")
        return {
            "success": False,
            "error": str(e),
            "server": {"host": host, "port": port},
            "timeout_seconds": timeout_seconds,
            "timing": {"total_ms": total_ms},
        }
    finally:
        try:
            sock.close()
        except Exception:
            pass


def run_single_task_service(
    prompt: str,
    model: str = "glm",
    timeout_ms: int = 120000,
    allowed_tools: List[str] = None,
) -> Dict[str, Any]:
    content = str(prompt or "").strip()
    if not content:
        return {"success": False, "error": "prompt is required"}

    token_out = get_valid_ai_token_service()
    if not token_out.get("success"):
        return {"success": False, "error": token_out.get("error", "failed to get valid ai token")}
    token = str(token_out.get("token") or "").strip()
    if not token:
        return {"success": False, "error": "missing token"}

    server = _load_ai_server_config()
    task_url = f"{server['base_url']}/api/v1/task"
    payload: Dict[str, Any] = {
        "model": str(model or "glm").strip() or "glm",
        "prompt": content,
        "timeout_ms": max(int(timeout_ms or 120000), 1000),
    }
    if allowed_tools:
        payload["allowed_tools"] = allowed_tools

    try:
        resp = requests.post(
            task_url,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
            },
            json=payload,
            timeout=max(int(payload["timeout_ms"] / 1000) + 5, 10),
        )
        data = resp.json()
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "task_url": task_url,
        }

    ok = resp.status_code == 200 and str(data.get("status", "")).lower() == "success"
    return {
        "success": ok,
        "http_status": resp.status_code,
        "task_url": task_url,
        "request": payload,
        "response": data,
        "error": "" if ok else str(data.get("error") or f"task failed, status={data.get('status')}"),
    }
