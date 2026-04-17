#!/usr/bin/env python3
import argparse
import json
import sys
from typing import Any, Dict, List

import requests

from services.ai_token_service import get_valid_ai_token_service


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="按 Chat Completions 协议直连调用 AI（/v1/chat/completions）。"
    )
    parser.add_argument("--base-url", default="http://claude.server22.jz", help="直连 API 基础地址")
    parser.add_argument("--token", default="", help="Bearer token；不传则自动从本地 ai_token_service 获取")
    parser.add_argument("--model", default="glm", help="模型名称，默认 glm")
    parser.add_argument("--system", default="", help="system 提示词（可选）")
    parser.add_argument("--prompt", required=True, help="用户输入 prompt")
    parser.add_argument("--temperature", type=float, default=0.7, help="采样温度")
    parser.add_argument("--max-tokens", type=int, default=2048, help="最大输出 token")
    parser.add_argument("--timeout", type=int, default=60, help="HTTP 超时秒数")
    return parser.parse_args()


def _resolve_token(input_token: str) -> str:
    token = str(input_token or "").strip()
    if token:
        return token
    out = get_valid_ai_token_service()
    if not out.get("success"):
        raise RuntimeError(f"获取 token 失败: {out.get('error', 'unknown error')}")
    token = str(out.get("token") or "").strip()
    if not token:
        raise RuntimeError("获取 token 失败: token 为空")
    return token


def _build_messages(system_prompt: str, user_prompt: str) -> List[Dict[str, str]]:
    messages: List[Dict[str, str]] = []
    if str(system_prompt or "").strip():
        messages.append({"role": "system", "content": str(system_prompt).strip()})
    messages.append({"role": "user", "content": str(user_prompt).strip()})
    return messages


def _extract_answer(payload: Dict[str, Any]) -> str:
    choices = payload.get("choices")
    if isinstance(choices, list) and choices:
        msg = choices[0].get("message") if isinstance(choices[0], dict) else {}
        if isinstance(msg, dict):
            content = msg.get("content")
            if content is not None:
                return str(content)
    return ""


def main() -> int:
    args = _parse_args()
    try:
        token = _resolve_token(args.token)
        url = f"{str(args.base_url).rstrip('/')}/v1/chat/completions"
        body = {
            "model": str(args.model).strip() or "glm",
            "messages": _build_messages(args.system, args.prompt),
            "temperature": float(args.temperature),
            "max_tokens": int(args.max_tokens),
            "stream": False,
        }
        response = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=max(int(args.timeout), 5),
        )
        data = response.json()
        if response.status_code >= 400:
            print(json.dumps({
                "success": False,
                "http_status": response.status_code,
                "error": data.get("error", data),
            }, ensure_ascii=False, indent=2))
            return 1

        answer = _extract_answer(data)
        print(json.dumps({
            "success": True,
            "http_status": response.status_code,
            "answer": answer,
            "raw": data,
        }, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({
            "success": False,
            "error": str(exc),
        }, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

