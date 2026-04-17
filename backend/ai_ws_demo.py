import json
import os
import socket
import subprocess

API = "http://claude.server22.jz"
# 建议通过环境变量传入，避免把密钥写入代码仓库
API_KEY = os.getenv("CLAUDE_API_KEY", "sk-n0S0p7CgwTcEHdUYLEccKlkxDwwGr2nMxvIbzdqhz1RiwyRv")
HOST = "claude.server22.jz"
PORT = 80


def get_token() -> str:
    result = subprocess.run(
        [
            "curl",
            "-s",
            "-X",
            "POST",
            f"{API}/api/v1/token",
            "-H",
            "Content-Type: application/json",
            "-d",
            json.dumps({"api_key": API_KEY}),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    raw = result.stdout.strip()
    if not raw:
        raise RuntimeError("token 接口返回为空，请检查 API 地址和网络连通性。")

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"token 接口返回非 JSON：{raw}") from exc

    # 兼容几种常见字段结构
    token = payload.get("token") or payload.get("access_token")
    if not token and isinstance(payload.get("data"), dict):
        token = payload["data"].get("token") or payload["data"].get("access_token")

    if not token:
        raise RuntimeError(
            "token 接口未返回 token 字段。"
            f"接口返回：{json.dumps(payload, ensure_ascii=False)}"
        )

    return token


def send(sock: socket.socket, msg: dict) -> None:
    sock.sendall((json.dumps(msg) + "\n").encode())


def recv(sock: socket.socket) -> dict:
    buf = b""
    sock.settimeout(120)
    while b"\n" not in buf:
        buf += sock.recv(4096)
    return json.loads(buf.strip())


def main() -> None:
    token = get_token()

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((HOST, PORT))
    sock.sendall(
        (
            f"GET /api/v1/session?token={token} HTTP/1.1\r\n"
            f"Host: {HOST}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n\r\n"
        ).encode()
    )

    resp = b""
    while b"\r\n\r\n" not in resp:
        resp += sock.recv(4096)
    if b" 101 " not in resp:
        raise RuntimeError(f"WebSocket 握手失败，响应头：{resp.decode(errors='replace')}")

    send(sock, {"type": "start", "model": "glm"})
    print(recv(sock))  # {"type": "started", ...}

    send(sock, {"type": "prompt", "content": "请记住数字99，回复OK"})
    print(recv(sock))  # {"type": "result", "data": {"result": "OK", ...}}

    send(sock, {"type": "prompt", "content": "我让你记住的数字是几？"})
    print(recv(sock))  # {"type": "result", "data": {"result": "99", ...}}

    send(sock, {"type": "end"})
    print(recv(sock))  # {"type": "ended", ...}

    sock.close()


if __name__ == "__main__":
    main()
