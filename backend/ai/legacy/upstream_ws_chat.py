#!/usr/bin/env python3
import argparse
import json
import socket
import sys


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="连接上游 AI 会话接口，进行终端连续对话。"
    )
    parser.add_argument(
        "--host",
        default="claude.server22.jz",
        help="上游服务 host，默认 claude.server22.jz",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=80,
        help="上游服务端口，默认 80",
    )
    parser.add_argument(
        "--token",
        required=True,
        help="上游 token（/api/v1/token 返回）",
    )
    parser.add_argument(
        "--model",
        default="glm",
        help="会话启动模型，默认 glm",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=180,
        help="socket 超时秒数，默认 180",
    )
    return parser.parse_args()


def _recv_http_header(sock: socket.socket) -> str:
    buf = b""
    while b"\r\n\r\n" not in buf:
        chunk = sock.recv(4096)
        if not chunk:
            raise RuntimeError("握手失败：连接被上游关闭。")
        buf += chunk
    return buf.decode(errors="ignore")


def _recv_json_line(sock: socket.socket) -> dict:
    buf = b""
    while b"\n" not in buf:
        chunk = sock.recv(4096)
        if not chunk:
            raise RuntimeError("连接已关闭，无法继续收消息。")
        buf += chunk
    line, _, _rest = buf.partition(b"\n")
    raw = line.decode(errors="ignore").strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return {"raw": raw}


def _send_json_line(sock: socket.socket, payload: dict) -> None:
    sock.sendall((json.dumps(payload, ensure_ascii=False) + "\n").encode())


def _extract_result_text(resp: dict) -> str:
    """
    从上游响应里提取可读结果文本，优先 data.result。
    """
    data = resp.get("data")
    if isinstance(data, dict):
        result = data.get("result")
        if result is not None:
            return str(result)
    result = resp.get("result")
    if result is not None:
        return str(result)
    return ""


def run_chat(host: str, port: int, token: str, model: str, timeout: int) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    sock.connect((host, port))

    req = (
        f"GET /api/v1/session?token={token} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        "\r\n"
    )
    sock.sendall(req.encode())
    header = _recv_http_header(sock)
    status_line = (header.splitlines() or [""])[0]
    if "101" not in status_line:
        raise RuntimeError(f"握手失败，响应：{status_line or header}")

    _send_json_line(sock, {"type": "start", "model": model})
    started = _recv_json_line(sock)
    print("started <=", json.dumps(started, ensure_ascii=False))
    print("已进入连续对话。输入 /exit 结束会话。")

    try:
        while True:
            try:
                text = input("chat> ").strip()
            except EOFError:
                text = "/exit"

            if not text:
                continue
            if text == "/exit":
                _send_json_line(sock, {"type": "end"})
                ended = _recv_json_line(sock)
                print("ended <=", json.dumps(ended, ensure_ascii=False))
                break

            _send_json_line(sock, {"type": "prompt", "content": text})
            resp = _recv_json_line(sock)
            result_text = _extract_result_text(resp)
            if result_text:
                print("AI <=", result_text)
            else:
                print("AI <=", json.dumps(resp, ensure_ascii=False))
    finally:
        try:
            sock.close()
        except Exception:
            pass


def main() -> int:
    args = _parse_args()
    try:
        run_chat(
            host=str(args.host).strip(),
            port=int(args.port),
            token=str(args.token).strip(),
            model=str(args.model).strip(),
            timeout=int(args.timeout),
        )
        return 0
    except KeyboardInterrupt:
        print("\n已中断。")
        return 130
    except Exception as exc:
        print(f"运行失败: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

