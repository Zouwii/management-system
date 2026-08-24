#!/usr/bin/env python3
"""Fetch read-only native DingTalk representations for selected v3 samples.

This script is intended to run on the project server, where the existing
DingTalk MCP gateway is configured. It writes only to the caller-provided
temporary output directory.
"""

from __future__ import annotations

import argparse
import json
import runpy
from pathlib import Path

import requests


SAMPLES = [
    ("01-speed-arbitration", "Obva6QBXJw9KMa5xi9eb2zjRWn4qY5Pr"),
    ("02-diagnosis-requirements", "r1R7q3QmWe7L0eawh7No92GwJxkXOEP2"),
    ("03-low-code-dictionary", "YMyQA2dXW79vMepgiwxgyeG1JzlwrZgb"),
    ("04-ros-interface", "EpGBa2Lm8azLmGpZC30Xo42yWgN7R35y"),
    ("05-agv-maintenance", "ZX6GRezwJl7KPA5zhQrvY4zGVdqbropQ"),
    ("06-simulation-http-api", "YQBnd5ExVEwO0vDjcj0jkpbv8yeZqMmz"),
]


def call(endpoint: str, name: str, arguments: dict) -> dict:
    response = requests.post(
        endpoint,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        json={
            "jsonrpc": "2.0",
            "id": f"rag-v3-{name}",
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
        timeout=120,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("error"):
        raise RuntimeError(str(payload["error"]))
    content = payload.get("result", {}).get("content") or []
    if not content:
        raise RuntimeError(f"{name} returned no content")
    text = content[0].get("text", "")
    return json.loads(text) if isinstance(text, str) else text


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    endpoint = runpy.run_path("/home/jz/zhr/dingtalk-download.py")["MCP_URL"]
    manifest = []
    for slug, node_id in SAMPLES:
        row = {"slug": slug, "node_id": node_id, "outputs": {}, "errors": {}}
        requests_to_make = {
            "markdown": ("get_document_content", {"nodeId": node_id, "format": "markdown"}),
            "jsonml": ("get_document_content", {"nodeId": node_id, "format": "jsonml"}),
            "outline": (
                "get_document_content",
                {"nodeId": node_id, "format": "jsonml", "scope": "outline"},
            ),
            "blocks": ("list_document_blocks", {"nodeId": node_id, "format": "element"}),
        }
        for suffix, (tool_name, arguments) in requests_to_make.items():
            try:
                result = call(endpoint, tool_name, arguments)
                path = args.output / f"{slug}.{suffix}.json"
                path.write_text(
                    json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                row["outputs"][suffix] = {
                    "file": path.name,
                    "bytes": path.stat().st_size,
                }
            except Exception as exc:
                row["errors"][suffix] = str(exc)
        manifest.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)

    (args.output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
