"""Teambition Open API wrapper via 钉钉代理.

Calls TB Open API (open.teambition.com) through the DingTalk proxy
(http://claude.server22.jz/api/dingtalk/proxy) which handles JWT auth.

Credentials are read from environment variables (DINGTALK_PROXY_TOKEN /
DINGTALK_UNION_ID), loaded from backend/.env by dotenv.
Runtime updates are persisted to backend/data/tb_proxy_credentials.json.

Usage:
    from base.onsite_problem.tb_proxy import fetch_task_with_comments, check_proxy_health
    ok, msg = check_proxy_health()
    result = fetch_task_with_comments(task_id="6a50ae41cf18f4c32f7ddf8b")
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

# ── proxy config ─────────────────────────────────────────────────
PROXY_URL = "http://claude.server22.jz/api/dingtalk/proxy"
TB_API_BASE = "https://open.teambition.com/api/v3"
REQUEST_TIMEOUT = 30

# Runtime credential update file (under data/, persisted across deploys)
_CREDENTIALS_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "tb_proxy_credentials.json"


def _get_proxy_credentials() -> Tuple[str, str]:
    """Read proxy token and union_id.

    Priority:
      1. Runtime update file (data/tb_proxy_credentials.json) — written by update_proxy_credentials()
      2. Environment variables (DINGTALK_PROXY_TOKEN / DINGTALK_UNION_ID, loaded from .env)
    """
    # 1. Check runtime update file
    if _CREDENTIALS_FILE.exists():
        try:
            cfg = json.loads(_CREDENTIALS_FILE.read_text())
            token = (cfg.get("token") or "").strip()
            union_id = (cfg.get("union_id") or "").strip()
            if token and union_id:
                return token, union_id
        except Exception:
            pass

    # 2. Fallback to env vars (from .env)
    token = os.environ.get("DINGTALK_PROXY_TOKEN", "").strip()
    union_id = os.environ.get("DINGTALK_UNION_ID", "").strip()

    if not token or not union_id:
        raise RuntimeError(
            "缺少 TB 代理凭据。请通过诊断终端获取 proxyToken 和 unionId，"
            "然后调用: curl -X POST http://localhost:5000/api/bt/onsite/update-proxy "
            '-H "Content-Type: application/json" '
            '-d \'{"proxyToken":"<token>","unionId":"<union_id>"}\''
        )

    return token, union_id


def _proxy_request(method: str, url: str, body: Optional[dict] = None) -> dict:
    """Send a request through the DingTalk proxy."""
    token, union_id = _get_proxy_credentials()

    proxy_body: Dict[str, Any] = {
        "url": url,
        "method": method,
        "headers": {"Content-Type": "application/json"},
    }
    if body is not None:
        proxy_body["body"] = body

    resp = requests.post(
        PROXY_URL,
        json=proxy_body,
        headers={
            "Content-Type": "application/json",
            "X-Proxy-Token": token,
            "X-User-Id": union_id,
        },
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, dict) and data.get("code") and data["code"] != 200:
        raise RuntimeError(f"TB API error: {data.get('errorMessage', data.get('code'))}")
    return data


def fetch_task_detail(task_id: str) -> dict:
    """Get task detail (customfields, metadata) via TB Open API.

    GET /api/v3/task/query?taskId=<taskId>
    """
    url = f"{TB_API_BASE}/task/query?taskId={task_id}"
    result = _proxy_request("GET", url)
    items = result.get("result", [])
    if not items:
        raise RuntimeError(f"task not found: {task_id}")
    return items[0]


def fetch_activities(task_id: str, max_pages: int = 10) -> List[dict]:
    """Get all activities (including comments) for a task.

    GET /api/v3/task/{taskId}/activity/list?pageSize=50
    Pages until nextPageToken is empty.
    """
    all_acts: List[dict] = []
    page_token = ""

    for _ in range(max_pages):
        url = f"{TB_API_BASE}/task/{task_id}/activity/list?pageSize=50"
        if page_token:
            url += f"&pageToken={page_token}"
        result = _proxy_request("GET", url)
        acts = result.get("result", [])
        if isinstance(acts, list):
            all_acts.extend(acts)
        page_token = result.get("nextPageToken", "")
        if not page_token:
            break

    return all_acts


def fetch_file_metadata(resource_ids: List[str]) -> List[dict]:
    """Get file metadata by resourceId.

    POST /api/v3/file/query/by-resource-ids
    Body: {"resourceIds": [...], "needSign": false}
    """
    if not resource_ids:
        return []
    result = _proxy_request(
        "POST",
        f"{TB_API_BASE}/file/query/by-resource-ids",
        {"resourceIds": resource_ids, "needSign": False},
    )
    return result.get("result", []) or []


def fetch_task_with_comments(task_id: str) -> Dict[str, Any]:
    """Fetch task detail + activities, build comments_json and attachments_json.

    Returns:
        {
            "task": {...},           # full task detail from API
            "comments_json": [...],  # comment stream
            "attachments_json": [...],  # attachment metadata stream
        }
    """
    task = fetch_task_detail(task_id)
    activities = fetch_activities(task_id)

    # ── Build comments_json ──
    comments_json: List[dict] = []
    comment_idx = 0
    comment_attachments: Dict[int, List[str]] = {}  # comment_idx -> [resource_id]

    for act in activities:
        if act.get("action") != "comment":
            continue
        comment_idx += 1
        content_raw = act.get("content", "")
        try:
            content_obj = json.loads(content_raw) if isinstance(content_raw, str) else content_raw
        except json.JSONDecodeError:
            content_obj = {"comment": content_raw}

        comment_text = content_obj.get("comment", "") if isinstance(content_obj, dict) else str(content_obj)
        file_ids = content_obj.get("files", []) if isinstance(content_obj, dict) else []

        comments_json.append({
            "idx": comment_idx,
            "content": comment_text,
            "creator_id": act.get("creatorId", ""),
            "create_time": act.get("createTime", ""),
            "attachment_indices": [],  # filled later
        })

        if file_ids:
            activity_id = act.get("id", "")
            for fid in file_ids:
                rid = f"task:{task_id}/activity:{activity_id}/file:{fid}"
                comment_attachments.setdefault(comment_idx, []).append(rid)

    # ── Build attachments_json ──
    attachments_json: List[dict] = []
    attach_idx = 0
    all_rids: List[str] = []

    # Collect customfield attachments
    cf_rids: List[Tuple[str, str]] = []  # (resource_id, cf_id)
    for cf in task.get("customfields", []) or []:
        if cf.get("type") not in ("work", "file"):
            continue
        cf_id = cf.get("cfId") or cf.get("customfieldId", "")
        for v in cf.get("value", []) or []:
            meta = v.get("metaString", "")
            try:
                m = json.loads(meta) if isinstance(meta, str) else meta
            except json.JSONDecodeError:
                continue
            rid = m.get("resourceId", "") if isinstance(m, dict) else ""
            if rid:
                cf_rids.append((rid, cf_id))
                all_rids.append(rid)

    # Collect comment attachments
    for c_idx, rids in comment_attachments.items():
        for rid in rids:
            all_rids.append(rid)
            # Will link after we build attachment entries

    # Fetch file metadata (batch)
    meta_map: Dict[str, dict] = {}
    if all_rids:
        # Split into chunks of 20
        for i in range(0, len(all_rids), 20):
            chunk = all_rids[i:i + 20]
            try:
                metas = fetch_file_metadata(chunk)
                for m in metas:
                    rid = m.get("resourceId", "")
                    if rid:
                        meta_map[rid] = m
            except Exception:
                pass

    # Build customfield attachments
    for rid, cf_id in cf_rids:
        attach_idx += 1
        meta = meta_map.get(rid, {})
        attachments_json.append({
            "idx": attach_idx,
            "resource_id": rid,
            "file_name": meta.get("fileName", ""),
            "file_size": meta.get("fileSize", 0),
            "mime_type": meta.get("mimeType", ""),
            "source": "customfield",
            "cf_id": cf_id,
            "comment_idx": None,
        })

    # Build comment attachments and link indices
    comment_attach_map: Dict[int, List[int]] = {}  # comment_idx -> [attach_idx]
    for c_idx, rids in comment_attachments.items():
        for rid in rids:
            attach_idx += 1
            meta = meta_map.get(rid, {})
            attachments_json.append({
                "idx": attach_idx,
                "resource_id": rid,
                "file_name": meta.get("fileName", ""),
                "file_size": meta.get("fileSize", 0),
                "mime_type": meta.get("mimeType", ""),
                "source": "comment",
                "cf_id": None,
                "comment_idx": c_idx,
            })
            comment_attach_map.setdefault(c_idx, []).append(attach_idx)

    # Fill attachment_indices in comments
    for c in comments_json:
        c["attachment_indices"] = comment_attach_map.get(c["idx"], [])

    return {
        "task": task,
        "comments_json": comments_json,
        "attachments_json": attachments_json,
    }


# ── credential management ──────────────────────────────────────

def check_proxy_health() -> Tuple[bool, str]:
    """Verify proxy credentials are valid by making a lightweight API call.

    Returns:
        (ok, message) — e.g. (True, "代理连接正常") or (False, "凭据已过期: ...")
    """
    try:
        token, union_id = _get_proxy_credentials()
    except RuntimeError as e:
        return False, str(e)

    try:
        # Lightweight check: GET project info (cheapest TB API call)
        resp = requests.post(
            PROXY_URL,
            json={
                "url": f"{TB_API_BASE}/project/query?projectId=616e6868a46ec51df166f4cd",
                "method": "GET",
                "headers": {"Content-Type": "application/json"},
            },
            headers={
                "Content-Type": "application/json",
                "X-Proxy-Token": token,
                "X-User-Id": union_id,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict) and data.get("code") and data["code"] != 200:
            return False, f"代理返回错误: code={data.get('code')}, msg={data.get('errorMessage', '')}"
        return True, "代理连接正常"
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response is not None else "?"
        if status == 401 or status == 403:
            return False, (
                "凭据已过期或无权限。请通过诊断终端 (diagkit) 获取新的 proxyToken 和 unionId，"
                "然后调用 POST /onsite/update-proxy 更新凭据。"
            )
        return False, f"代理请求失败: HTTP {status}"
    except requests.exceptions.ConnectionError:
        return False, "无法连接代理服务器 (claude.server22.jz)"
    except requests.exceptions.Timeout:
        return False, "代理请求超时"
    except Exception as e:
        return False, f"健康检查异常: {e}"


def update_proxy_credentials(token: str, union_id: str) -> Tuple[bool, str]:
    """Persist proxy credentials to data/tb_proxy_credentials.json.

    On next read, _get_proxy_credentials() will prefer these over .env values.
    The file survives deployments (data/ is preserved by deploy script).
    """
    token = (token or "").strip()
    union_id = (union_id or "").strip()
    if not token or not union_id:
        return False, "token 和 union_id 不能为空"

    try:
        _CREDENTIALS_FILE.parent.mkdir(parents=True, exist_ok=True)
        _CREDENTIALS_FILE.write_text(
            json.dumps({"token": token, "union_id": union_id}, ensure_ascii=False, indent=2)
        )
        return True, "凭据已更新"
    except Exception as e:
        return False, f"写入凭据文件失败: {e}"
