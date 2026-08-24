#!/usr/bin/env python3
"""List DingTalk MCP tool schemas without printing gateway credentials."""

from __future__ import annotations

import json
import re
import runpy

import requests


def main() -> None:
    downloader = runpy.run_path("/home/jz/zhr/dingtalk-download.py")
    endpoint = downloader["MCP_URL"]
    response = requests.post(
        endpoint,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        json={"jsonrpc": "2.0", "id": "rag-v3-probe", "method": "tools/list", "params": {}},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    tools = payload.get("result", {}).get("tools") or []
    safe = [
        {
            "name": tool.get("name"),
            "description": tool.get("description"),
            "inputSchema": tool.get("inputSchema"),
        }
        for tool in tools
    ]
    relevant = [
        tool for tool in safe
        if re.search(r"search|list_document_blocks|get_document_content|list_nodes", tool["name"] or "")
    ]
    print(json.dumps({
        "tool_count": len(safe),
        "tool_names": [tool["name"] for tool in safe],
        "relevant_tools": relevant,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
