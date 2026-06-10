"""DingTalk knowledge base API client.

Verified API endpoints (2026-05-26):

  Browse:
    GET /v2.0/wiki/workspaces?operatorId=<unionId>
    GET /v2.0/wiki/nodes?workspaceId=<id>&operatorId=<unionId>&parentNodeId=<id>
    GET /v2.0/wiki/nodes/<nodeId>?operatorId=<unionId>

  Content:
    GET /v1.0/doc/suites/documents/<nodeId>/blocks?operatorId=<unionId>
    GET /v1.0/doc/workbooks/<nodeId>/sheets?operatorId=<unionId>
    GET /v1.0/doc/workbooks/<nodeId>/sheets/<sheetId>/ranges/<range>?operatorId=<unionId>

  Search:
    POST /v2.0/storage/dentries/search?operatorId=<unionId>
    GET /v1.0/doc/docs?operatorId=<unionId>&workspaceId=<id>&keyword=<kw>&maxResults=<n>

Auth: x-acs-dingtalk-access-token header (app-level, from dingtalk_client)
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from base.dingtalk_client import get_valid_access_token

# ── knowledge base priority config ─────────────────────────────

_HARDCODED_WORKSPACES: Dict[str, int] = {
    "1oam4Sk7BMLXxn8K": 0,    # 本体开发部
    "By8jQSbJyWLAL30M": 1,    # 研发共享文档
    "yq8ZkS3KYJW4enaX": 2,    # 研发体系文档【JZ-TOTAL】
    "9Bv51SJGoKxPBjv3": 3,    # 研发体系全员文档库
    "X1v4RS7ybR4GeZ8P": 4,    # 研发共享文档（非公开）
    "5zaVASrJnl5bDo8y": 5,    # 产品专项知识库（2023上半年-2025年）
    "9Bv51SWzXGOJOzv3": 6,    # 研发专项知识库（2023上半年-2026年）
    "bJvOOSLN3yLzGgvK": 7,    # 订单专项知识库（2022-2025）
    "OQ0xySKEGYKEG48B": 8,    # 产品信息门户
    "MJ0pDSwlOEkMqQ0E": 9,    # 订单项目信息门户
}


def get_known_workspaces() -> Dict[str, int]:
    """Read workspace config from kb_workspaces.json, fall back to hardcoded list.

    The JSON file lives at ``backend/kb_workspaces.json`` and follows the same
    pattern as ``ids.json``::

        {
          "kb_workspaces": {
            "本体开发部": { "workspace_id": "...", "enabled": true, "priority": 0 },
            ...
          }
        }

    Only entries with ``enabled: true`` are returned.
    """
    cfg_path = Path(__file__).resolve().parent.parent / "base" / "kb_workspaces.json"
    if cfg_path.exists():
        try:
            raw = cfg_path.read_text(encoding="utf-8").strip()
            if raw:
                data = json.loads(raw)
                workspaces = data.get("kb_workspaces", {})
                if isinstance(workspaces, dict):
                    result: Dict[str, int] = {}
                    for _name, entry in workspaces.items():
                        if not isinstance(entry, dict):
                            continue
                        if not entry.get("enabled", False):
                            continue
                        ws_id = str(entry.get("workspace_id", "")).strip()
                        if not ws_id:
                            continue
                        priority = int(entry.get("priority", 999))
                        result[ws_id] = priority
                    if result:
                        return result
        except Exception:
            pass
    return dict(_HARDCODED_WORKSPACES)


def workspace_priority(workspace_id: str) -> int:
    known = get_known_workspaces()
    return known.get(workspace_id, 999)


def sort_workspaces(workspaces: List[dict]) -> List[dict]:
    """Sort workspaces by priority (known first)."""
    return sorted(workspaces, key=lambda w: workspace_priority(w.get("workspaceId", "")))


# ── logging ────────────────────────────────────────────────────

def _log(entry: dict) -> None:
    try:
        log_file = Path(__file__).resolve().parent.parent.parent / "runtime" / "logs" / "ai_debug.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with log_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass

    # Also feed to the in-memory monitor
    try:
        from base.api_monitor import record_api_call
        record_api_call(
            endpoint=entry.get("endpoint", "?"),
            status=entry.get("status", 0),
            latency_ms=entry.get("latency_ms", 0),
            error=entry.get("error", ""),
            source="kb_sync",
        )
    except Exception:
        pass


# ── client ─────────────────────────────────────────────────────

class DingTalkKnowledgeClient:
    """Client for verified DingTalk knowledge base APIs."""

    def __init__(self, union_id: str):
        self.base_url = "https://api.dingtalk.com"
        self.union_id = union_id
        self._timeout = 30

    def _token(self) -> str:
        result = get_valid_access_token({})
        if not result.get("ok"):
            raise RuntimeError(result.get("error", "failed to get access_token"))
        return result["access_token"]

    def _headers(self) -> Dict[str, str]:
        return {
            "x-acs-dingtalk-access-token": self._token(),
            "Content-Type": "application/json",
        }

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        start = time.time()
        params = dict(params or {})
        try:
            resp = requests.get(url, headers=self._headers(), params=params, timeout=self._timeout)
            elapsed = int((time.time() - start) * 1000)
            try:
                data = resp.json()
            except Exception:
                data = {"raw": resp.text}
            _log({
                "ts": int(time.time()), "phase": "kb_api_get",
                "endpoint": path, "status": resp.status_code, "latency_ms": elapsed,
            })
            return {"ok": 200 <= resp.status_code < 300, "data": data, "status": resp.status_code}
        except requests.RequestException as exc:
            _log({"ts": int(time.time()), "phase": "kb_api_error", "endpoint": path, "error": str(exc)})
            return {"ok": False, "error": str(exc), "data": {}}

    def _post(self, path: str, body: Dict[str, Any], params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        start = time.time()
        params = dict(params or {})
        try:
            resp = requests.post(url, headers=self._headers(), params=params, json=body, timeout=self._timeout)
            elapsed = int((time.time() - start) * 1000)
            try:
                data = resp.json()
            except Exception:
                data = {"raw": resp.text}
            _log({
                "ts": int(time.time()), "phase": "kb_api_post",
                "endpoint": path, "status": resp.status_code, "latency_ms": elapsed,
            })
            return {"ok": 200 <= resp.status_code < 300, "data": data, "status": resp.status_code}
        except requests.RequestException as exc:
            _log({"ts": int(time.time()), "phase": "kb_api_error", "endpoint": path, "error": str(exc)})
            return {"ok": False, "error": str(exc), "data": {}}

    # ── browse ─────────────────────────────────────────────────

    def list_workspaces(self) -> Dict[str, Any]:
        """List all knowledge base workspaces accessible to this user.

        GET /v2.0/wiki/workspaces?operatorId=<unionId>
        """
        result = self._get("/v2.0/wiki/workspaces", {"operatorId": self.union_id})
        if not result["ok"]:
            return result

        workspaces = result.get("data", {}).get("workspaces") or []
        items = []
        for w in workspaces:
            ws_id = w.get("workspaceId", "")
            items.append({
                "workspaceId": ws_id,
                "name": w.get("name", ""),
                "rootNodeId": w.get("rootNodeId", ""),
                "createTime": w.get("createTime", ""),
                "modifiedTime": w.get("modifiedTime", ""),
                "creatorId": w.get("creatorId", ""),
                "priority": workspace_priority(ws_id),
            })
        items.sort(key=lambda x: x["priority"])
        return {"ok": True, "data": items}

    def list_nodes(self, workspace_id: str, parent_node_id: str = "") -> Dict[str, Any]:
        """List child nodes under a workspace root or parent node.

        GET /v2.0/wiki/nodes?workspaceId=<id>&operatorId=<unionId>&parentNodeId=<id>
        """
        params: Dict[str, Any] = {
            "workspaceId": workspace_id,
            "operatorId": self.union_id,
        }
        if parent_node_id:
            params["parentNodeId"] = parent_node_id

        result = self._get("/v2.0/wiki/nodes", params)
        if not result["ok"]:
            return result

        nodes = result.get("data", {}).get("nodes") or []
        items = []
        for n in nodes:
            items.append({
                "nodeId": n.get("nodeId", ""),
                "name": n.get("name", ""),
                "type": n.get("type", "FILE").upper(),    # FILE / FOLDER
                "category": n.get("category", ""),        # ALIDOC / WORKBOOK / OTHER
                "hasChildren": n.get("hasChildren", False),
                "url": n.get("url", ""),
                "size": n.get("size", 0),
                "createTime": n.get("createTime", ""),
                "modifiedTime": n.get("modifiedTime", ""),
                "workspaceId": workspace_id,
            })
        return {"ok": True, "data": items}

    def get_node_detail(self, node_id: str) -> Dict[str, Any]:
        """Get metadata for a single node.

        GET /v2.0/wiki/nodes/<nodeId>?operatorId=<unionId>

        Note: This returns metadata only, NOT document content.
        Use get_document_blocks() for content.
        """
        result = self._get(f"/v2.0/wiki/nodes/{node_id}", {"operatorId": self.union_id})
        if not result["ok"]:
            return result

        node = result.get("data", {}).get("node") or result.get("data", {})
        return {
            "ok": True,
            "data": {
                "nodeId": node.get("nodeId", node_id),
                "name": node.get("name", ""),
                "type": (node.get("type") or "FILE").upper(),
                "category": node.get("category", ""),
                "hasChildren": node.get("hasChildren", False),
                "url": node.get("url", ""),
                "size": node.get("size", 0),
                "workspaceId": node.get("workspaceId", ""),
                "createTime": node.get("createTime", ""),
                "modifiedTime": node.get("modifiedTime", ""),
                "creatorId": node.get("creatorId", ""),
                "modifierId": node.get("modifierId", ""),
                "extension": node.get("extension", ""),
            },
        }

    # ── content ────────────────────────────────────────────────

    def get_document_blocks(self, node_id: str) -> Dict[str, Any]:
        """Get document content as block array.

        GET /v1.0/doc/suites/documents/<nodeId>/blocks?operatorId=<unionId>

        Returns result.data: list of {blockType, paragraph/heading/..., index, id}
        If the document is a workbook, returns error with "WORKBOOK" hint.
        """
        result = self._get(
            f"/v1.0/doc/suites/documents/{node_id}/blocks",
            {"operatorId": self.union_id},
        )
        if not result["ok"]:
            return result

        blocks = result.get("data", {}).get("result", {}).get("data") or []
        return {"ok": True, "data": blocks}

    def get_workbook_sheets(self, node_id: str) -> Dict[str, Any]:
        """List all sheets in a workbook.

        GET /v1.0/doc/workbooks/<nodeId>/sheets?operatorId=<unionId>
        """
        result = self._get(
            f"/v1.0/doc/workbooks/{node_id}/sheets",
            {"operatorId": self.union_id},
        )
        if not result["ok"]:
            return result

        sheets = result.get("data", {}).get("value") or []
        return {"ok": True, "data": sheets}

    def get_workbook_range(self, node_id: str, sheet_id: str, range_spec: str = "A1:Z500") -> Dict[str, Any]:
        """Read cell data from a workbook sheet range.

        GET /v1.0/doc/workbooks/<nodeId>/sheets/<sheetId>/ranges/<range>?operatorId=<unionId>
        """
        result = self._get(
            f"/v1.0/doc/workbooks/{node_id}/sheets/{sheet_id}/ranges/{range_spec}",
            {"operatorId": self.union_id},
        )
        if not result["ok"]:
            return result

        values = result.get("data", {}).get("values") or []
        return {"ok": True, "data": values}

    # ── search ─────────────────────────────────────────────────

    def search_documents(self, keyword: str, max_results: int = 10) -> Dict[str, Any]:
        """Full-text search across all accessible documents.

        POST /v2.0/storage/dentries/search?operatorId=<unionId>
        Body: {"keyword": "<keyword>"}
        """
        result = self._post(
            "/v2.0/storage/dentries/search",
            {"keyword": keyword},
            {"operatorId": self.union_id},
        )
        if not result["ok"]:
            return result

        items = result.get("data", {}).get("items") or []
        results = []
        for it in items[:max_results]:
            results.append({
                "dentryUuid": it.get("dentryUuid", ""),
                "name": it.get("name", ""),
                "spaceName": it.get("spaceName", ""),
                "spaceId": it.get("spaceId", it.get("workspaceId", "")),
                "creatorName": it.get("creatorName", it.get("creator", "")),
                "modifierName": it.get("modifierName", it.get("modifier", "")),
                "createTime": it.get("createTime", ""),
                "modifyTime": it.get("modifyTime", ""),
                "extension": it.get("extension", ""),
                "url": it.get("url", ""),
            })
        return {"ok": True, "data": results}

    def search_in_workspace(self, workspace_id: str, keyword: str, max_results: int = 10) -> Dict[str, Any]:
        """Search documents within a specific knowledge base.

        GET /v1.0/doc/docs?operatorId=<unionId>&workspaceId=<id>&keyword=<kw>&maxResults=<n>
        """
        result = self._get(
            "/v1.0/doc/docs",
            {
                "operatorId": self.union_id,
                "workspaceId": workspace_id,
                "keyword": keyword,
                "maxResults": str(max_results),
            },
        )
        if not result["ok"]:
            return result

        docs = result.get("data", {}).get("docs") or result.get("data", {}).get("items") or []
        return {"ok": True, "data": docs}
