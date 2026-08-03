"""Download DingTalk documents as Markdown and persist them safely.

This module intentionally keeps Markdown parsing minimal.  The downloaded
Markdown is the document body used by the existing chunker; richer AST/image
processing can be added later without changing the sync pipeline contract.
"""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List

import requests

from ai.knowledge.models import KbDocument
from base.db.engine import KbSessionLocal


def _positive_int_env(name: str, default: int) -> int:
    try:
        return max(1, int(str(os.getenv(name, default)).strip()))
    except (TypeError, ValueError):
        return default


def _extract_markdown(response: requests.Response) -> tuple[str, dict]:
    """Extract Markdown from the JSON-RPC response returned by DingTalk MCP."""
    response.raise_for_status()
    payload = response.json()
    if payload.get("error"):
        raise RuntimeError(str(payload["error"]))

    content_items = payload.get("result", {}).get("content") or []
    if not content_items:
        raise RuntimeError("MCP response has no content")

    text_payload = content_items[0].get("text", "")
    document = json.loads(text_payload) if isinstance(text_payload, str) else text_payload
    if not isinstance(document, dict):
        raise RuntimeError("MCP document payload is not an object")
    if document.get("success") is False:
        raise RuntimeError(str(document.get("errorMsg") or "MCP document download failed"))

    markdown = document.get("markdown")
    if not isinstance(markdown, str) or not markdown.strip():
        raise RuntimeError("MCP document contains empty markdown")
    return markdown, document


def _download_one(document: dict, mcp_url: str, timeout: int) -> dict:
    node_id = str(document.get("node_id") or "").strip()
    if not node_id:
        return {**document, "ok": False, "error": "missing node_id"}

    payload = {
        "jsonrpc": "2.0",
        "id": node_id,
        "method": "tools/call",
        "params": {
            "name": "get_document_content",
            "arguments": {"nodeId": node_id},
        },
    }
    try:
        response = requests.post(
            mcp_url,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            json=payload,
            timeout=timeout,
        )
        markdown, source_payload = _extract_markdown(response)
        return {
            **document,
            "ok": True,
            "markdown": markdown,
            "source_payload": source_payload,
        }
    except Exception as exc:
        return {**document, "ok": False, "error": str(exc)}


def download_markdown_documents(
    documents: Iterable[dict],
    *,
    mcp_url: str = "",
    workers: int = 0,
    timeout: int = 0,
) -> dict:
    """Download a collection of ``{node_id, title, workspace_id}`` records."""
    items = [dict(item) for item in documents]
    if not items:
        return {"ok": True, "downloaded": [], "failed": [], "total": 0}

    resolved_url = str(mcp_url or os.getenv("DINGTALK_KB_MCP_URL") or "").strip()
    if not resolved_url:
        return {
            "ok": False,
            "downloaded": [],
            "failed": [
                {**item, "ok": False, "error": "missing DINGTALK_KB_MCP_URL"}
                for item in items
            ],
            "total": len(items),
            "error": "missing DINGTALK_KB_MCP_URL",
        }

    worker_count = workers or _positive_int_env("DINGTALK_KB_MCP_WORKERS", 8)
    request_timeout = timeout or _positive_int_env("DINGTALK_KB_MCP_TIMEOUT", 60)
    results: List[dict] = []
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = [
            executor.submit(_download_one, item, resolved_url, request_timeout)
            for item in items
        ]
        for future in as_completed(futures):
            results.append(future.result())

    downloaded = [item for item in results if item.get("ok")]
    failed = [item for item in results if not item.get("ok")]
    return {
        "ok": not failed,
        "downloaded": downloaded,
        "failed": failed,
        "total": len(items),
    }


def persist_downloaded_markdown(download_result: dict) -> dict:
    """Store successful Markdown downloads without overwriting data on failure."""
    downloaded = download_result.get("downloaded") or []
    failed = download_result.get("failed") or []
    now = datetime.now(timezone.utc)
    changed_ids: List[str] = []
    unchanged_ids: List[str] = []
    missing_ids: List[str] = []

    db = KbSessionLocal()
    try:
        for item in downloaded:
            node_id = str(item.get("node_id") or "").strip()
            row = db.query(KbDocument).filter(KbDocument.node_id == node_id).first()
            if row is None:
                missing_ids.append(node_id)
                continue

            markdown = str(item.get("markdown") or "")
            if row.content == markdown:
                unchanged_ids.append(node_id)
            else:
                row.content = markdown
                changed_ids.append(node_id)
            source_payload = dict(item.get("source_payload") or {})
            source_payload["_management_system"] = {
                "source": "mcp_markdown",
                "contentRemoteModifiedTime": str(
                    item.get("remote_modified_at") or ""
                ),
            }
            row.raw_json = json.dumps(source_payload, ensure_ascii=False)
            row.fetch_status = "success"
            row.fail_reason = ""
            row.synced_at = now
            row.updated_at = now

        for item in failed:
            node_id = str(item.get("node_id") or "").strip()
            row = db.query(KbDocument).filter(KbDocument.node_id == node_id).first()
            if row is not None:
                # A failed refresh must not make the last known-good body
                # unavailable.  Only documents with no usable body are failed.
                row.fetch_status = "success" if (row.content or "").strip() else "failed"
                row.fail_reason = str(item.get("error") or "download failed")[:500]
                row.updated_at = now

        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    return {
        "ok": not failed and not missing_ids,
        "changedIds": changed_ids,
        "changed": len(changed_ids),
        "unchanged": len(unchanged_ids),
        "failed": len(failed),
        "missing": len(missing_ids),
        "errors": [
            {"nodeId": item.get("node_id", ""), "error": item.get("error", "")}
            for item in failed[:20]
        ],
    }
