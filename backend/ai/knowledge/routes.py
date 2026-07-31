"""HTTP routes for knowledge base document browsing, sync, and chat.

Endpoints:
  GET  /ai/knowledge/workspaces                    - List knowledge bases (sorted by priority)
  GET  /ai/knowledge/workspaces/<ws_id>/nodes      - Browse document tree
  GET  /ai/knowledge/documents/<node_id>           - Get parsed document content (blocks -> markdown)
  POST /ai/knowledge/sync                          - Walk single workspace and cache documents
  POST /ai/knowledge/sync-all                      - Sync all known workspaces (documents only)
  POST /ai/knowledge/sync-and-embedding            - Full pipeline: sync -> rechunk -> embed
  POST /ai/knowledge/search                        - Search via DingTalk API
  POST /ai/knowledge/chunks/search                 - Local search on kb_chunks (keyword/vector/hybrid)
  POST /ai/knowledge/rechunk                       - Re-chunk + auto reembed
  POST /ai/knowledge/reembed                       - Embed chunks into pgvector
  POST /ai/knowledge/chat/session                  - Create chat session
  GET  /ai/knowledge/chat                          - SSE knowledge-base chat
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import List

from flask import request, session

from ai.knowledge.models import KbNode, KbDocument
from ai.knowledge.parser import parse_document
from ai.knowledge.service import DingTalkKnowledgeClient
from base.db.engine import KbSessionLocal, SessionLocal


# ── helpers ────────────────────────────────────────────────────

def _current_union_id() -> str:
    """优先从 session 获取用户，失败回退到 DB fallback。"""
    auth = session.get("auth_user") or {}
    user_id = ""
    if isinstance(auth, dict):
        for key in ("union_id", "unionId", "dingtalkUserId"):
            union_id = str(auth.get(key) or "").strip()
            if union_id:
                return union_id
        user_id = str(auth.get("user_id") or "")
    if user_id:
        try:
            from base.db.orm import UserCharacter as DbUserCharacter
            db = SessionLocal()
            try:
                row = db.query(DbUserCharacter).filter(DbUserCharacter.user_id == user_id).first()
                if row and row.union_id:
                    return row.union_id
            finally:
                db.close()
        except Exception:
            pass

    # Fallback: for admin/scenario use, grab any available union_id from DB
    try:
        from base.db.orm import UserCharacter as DbUserCharacter
        db = SessionLocal()
        try:
            row = db.query(DbUserCharacter).filter(
                DbUserCharacter.union_id.isnot(None),
                DbUserCharacter.union_id != ""
            ).first()
            if row and row.union_id:
                return row.union_id
        finally:
            db.close()
    except Exception:
        pass

    return ""


def _dt_to_iso(dt) -> str:
    if dt is None:
        return ""
    if isinstance(dt, str):
        return dt
    return dt.astimezone(timezone.utc).isoformat()


# ── cache helpers ──────────────────────────────────────────────

def _cached_document(node_id: str) -> dict | None:
    db = KbSessionLocal()
    try:
        row = db.query(KbDocument).filter(KbDocument.node_id == node_id).first()
        if row and row.content:
            return {
                "nodeId": row.node_id,
                "title": row.title,
                "workspaceId": row.workspace_id,
                "content": row.content,
                "format": "markdown",
                "source": "cache",
                "syncedAt": _dt_to_iso(row.synced_at),
            }
        return None
    finally:
        db.close()


# ── workspace sync (module-level, shared with auto_sync) ────────

def _parse_dingtalk_time(ts_str: str):
    """钉钉时间格式: 2026-07-23T12:17Z → datetime(UTC)"""
    if not ts_str:
        return None
    try:
        return datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
    except Exception:
        return None


def _upsert_node(db, node_id: str, workspace_id: str, parent_id: str,
                 name: str, node_type: str, category: str,
                 has_children: bool, depth: int, breadcrumb: str,
                 remote_modified_at, now: datetime):
    """Upsert a kb_node. Returns True if new or changed."""
    existing = db.query(KbNode).filter(KbNode.node_id == node_id).first()
    rmt = _parse_dingtalk_time(remote_modified_at) if isinstance(remote_modified_at, str) else remote_modified_at
    changed = False

    if existing:
        if (existing.name != name or existing.category != category or
            existing.has_children != has_children or existing.breadcrumb != breadcrumb or
            existing.depth != depth):
            changed = True
        existing.name = name
        existing.parent_id = parent_id
        existing.category = category
        existing.has_children = has_children
        existing.depth = depth
        existing.breadcrumb = breadcrumb
        existing.node_type = node_type
        existing.remote_modified_at = rmt
        existing.sync_status = "synced"
        existing.sync_error = ""
        existing.synced_at = now
        existing.updated_at = now
    else:
        db.add(KbNode(
            node_id=node_id, workspace_id=workspace_id, parent_id=parent_id,
            name=name, node_type=node_type, category=category,
            has_children=has_children, depth=depth, breadcrumb=breadcrumb,
            remote_modified_at=rmt, sync_status="synced",
            synced_at=now, created_at=now, updated_at=now))
        changed = True
    return changed


def _upsert_document(db, node_id: str, workspace_id: str, title: str,
                     content: str, raw_json: str, now: datetime) -> bool:
    """Upsert a kb_document. Returns True if content changed."""
    existing = db.query(KbDocument).filter(KbDocument.node_id == node_id).first()
    changed = False

    if existing:
        if existing.content != content:
            changed = True
        existing.title = title
        existing.content = content
        existing.raw_json = raw_json
        existing.fetch_status = "success"
        existing.fail_reason = ""
        existing.synced_at = now
        existing.updated_at = now
    else:
        db.add(KbDocument(
            node_id=node_id, workspace_id=workspace_id, title=title,
            content=content, raw_json=raw_json, fetch_status="success",
            synced_at=now, created_at=now, updated_at=now))
        changed = True
    return changed


def _sync_workspace(client, workspace_id: str, root_id: str, limit: int = 0,
                    check_modified: bool = False) -> dict:
    """新 schema 同步: 遍历目录树 → kb_nodes, 下载正文 → kb_documents.

    check_modified=False: 跳过已同步的 ALIDOC 文档（不做全量对比）。
    check_modified=True:  对比 remote_modified_at，重拉已变更文档。

    raw_json 置空 —— markdown 正文后续由 MCP 下载脚本 + fill-markdown 接口回填。

    Returns {syncedNodes, syncedDocs, syncedDocIds, changedDocIds, failedNodes,
             failedDocs, skippedWorkbooks, skippedCached, skippedUnchanged}.
    """
    synced_node_ids: List[str] = []
    synced_doc_ids: List[dict] = []
    changed_doc_ids: List[str] = []
    failed_nodes: List[dict] = []
    failed_docs: List[dict] = []
    skipped_workbooks: int = 0
    skipped_cached: int = 0
    skipped_unchanged: int = 0

    db = KbSessionLocal()
    now = datetime.now(timezone.utc)

    # 预加载已有文档缓存（用于增量判断）
    try:
        cached_docs = {
            r.node_id: {"content": r.content or "", "remote_modified_at": None}
            for r in db.query(KbDocument).filter(
                KbDocument.workspace_id == workspace_id,
                KbDocument.fetch_status == "success"
            ).all()
        }
    finally:
        pass  # db is kept open for the walk

    ws_name = workspace_id  # will be updated from root node
    BATCH_SIZE = 100  # 每处理 100 个节点 commit 一次

    def _walk(parent_id: str, breadcrumb: str, depth: int):
        nonlocal skipped_workbooks, skipped_cached, skipped_unchanged, ws_name

        if limit and len(synced_doc_ids) >= limit:
            return

        result = client.list_nodes(workspace_id, parent_id)
        if not result.get("ok"):
            err = result.get("error", "")
            status = result.get("status", "?")
            failed_nodes.append({"parentId": parent_id, "error": err, "status": status})
            print(f"[sync-error] list_nodes failed parentId={parent_id} status={status} error={err}")
            return

        for n in result["data"]:
            if limit and len(synced_doc_ids) >= limit:
                return

            nid = n["nodeId"]
            ntype = n["type"]
            name = n["name"]
            cat = (n.get("category") or "").strip().upper()
            hc = bool(n.get("hasChildren", False))
            rmt = n.get("modifiedTime", "")
            bc = breadcrumb + " / " + name if breadcrumb else name

            # ── 写入 kb_nodes（FOLDER + FILE 都写）──
            node_changed = _upsert_node(
                db, nid, workspace_id, parent_id, name, ntype, cat,
                hc, depth, bc, rmt, now)
            synced_node_ids.append(nid)

            # 批量 commit：每 BATCH_SIZE 个节点提交一次
            if len(synced_node_ids) % BATCH_SIZE == 0:
                try:
                    db.commit()
                except Exception as e:
                    db.rollback()
                    print(f"[sync-error] batch commit failed: {e}")

            if ntype == "FOLDER":
                # 继续递归
                _walk(nid, bc, depth + 1)

            elif ntype == "FILE":
                # 只处理 ALIDOC
                if cat != "ALIDOC":
                    skipped_workbooks += 1
                    continue

                # 增量跳过逻辑
                if not check_modified:
                    cached = cached_docs.get(nid)
                    if cached and cached["content"]:
                        skipped_cached += 1
                        continue

                if check_modified:
                    cached = cached_docs.get(nid)
                    if cached and cached["content"]:
                        last_rmt = cached.get("remote_modified_at")
                        cur_rmt = _parse_dingtalk_time(rmt)
                        if last_rmt and cur_rmt and cur_rmt <= last_rmt:
                            skipped_unchanged += 1
                            continue

                # 下载正文
                try:
                    blocks_resp = client.get_document_blocks(nid)
                    if not blocks_resp.get("ok"):
                        err = blocks_resp.get("error", "")
                        st = blocks_resp.get("status", "?")
                        failed_docs.append({"nodeId": nid, "title": name, "error": err, "status": st})
                        print(f"[sync-error] blocks failed nodeId={nid} title={name} status={st} error={err}")
                        continue

                    parsed = parse_document(blocks_resp["data"], "blocks")
                    content = parsed["markdown"]

                    doc_changed = _upsert_document(
                        db, nid, workspace_id, name, content, "", now)
                    synced_doc_ids.append({
                        "node_id": nid, "title": name, "breadcrumb": bc,
                    })
                    if doc_changed:
                        changed_doc_ids.append(nid)

                except Exception as e:
                    failed_docs.append({"nodeId": nid, "title": name, "error": str(e)})
                    print(f"[sync-error] exception nodeId={nid} title={name} error={str(e)}")

    # 写入 root 节点
    _upsert_node(db, root_id, workspace_id, "", ws_name, "FOLDER", "", True, 0, ws_name, None, now)

    # 开始遍历
    try:
        _walk(root_id, ws_name, 1)
        db.commit()  # 最终提交剩余节点
    except Exception as e:
        db.rollback()
        print(f"[sync-error] walk exception: {e}")
    finally:
        db.close()

    return {
        "syncedNodes": len(synced_node_ids),
        "syncedDocs": len(synced_doc_ids),
        "syncedDocIds": synced_doc_ids,
        "changedDocIds": changed_doc_ids,
        "failedNodes": len(failed_nodes),
        "failedDocs": len(failed_docs),
        "skippedWorkbooks": skipped_workbooks,
        "skippedCached": skipped_cached,
        "skippedUnchanged": skipped_unchanged,
        "errors": (failed_nodes + failed_docs)[:20],
    }


# ── route registration ─────────────────────────────────────────

def register(bp, ok, fail):

    def _require_api_enabled():
        """硬限检查：knowledge_sync_enabled='false' 时阻止所有钉钉 API 调用"""
        from base.config.service import is_sync_enabled
        if not is_sync_enabled():
            return fail("all DingTalk API calls are temporarily blocked (hard limit)", code=503, data={})
        return None

    @bp.route("/ai/knowledge/workspaces", methods=["GET"])
    def ai_knowledge_workspaces():
        """List knowledge bases accessible to the current user, sorted by priority."""
        union_id = _current_union_id()
        if not union_id:
            return fail("not logged in — unable to determine user identity", code=401)

        blocked = _require_api_enabled()
        if blocked:
            return blocked

        client = DingTalkKnowledgeClient(union_id)
        try:
            result = client.list_workspaces()
            if not result.get("ok"):
                return fail(result.get("error", "failed"), code=result.get("status", 502))

            return ok({"workspaces": result["data"]})
        except Exception as e:
            return fail(str(e), code=500)

    @bp.route("/ai/knowledge/workspaces/<workspace_id>/nodes", methods=["GET"])
    def ai_knowledge_nodes(workspace_id):
        """List nodes under a workspace root or parent node.

        Query params: node_id (optional, default = root)
        """
        union_id = _current_union_id()
        if not union_id:
            return fail("not logged in", code=401)

        blocked = _require_api_enabled()
        if blocked:
            return blocked

        parent_id = request.args.get("node_id", "").strip()
        client = DingTalkKnowledgeClient(union_id)
        try:
            result = client.list_nodes(workspace_id, parent_id)
            if not result.get("ok"):
                return fail(result.get("error", "failed"), code=result.get("status", 502),
                            data={"workspaceId": workspace_id, "parentId": parent_id})

            return ok({
                "workspaceId": workspace_id,
                "parentId": parent_id or "root",
                "nodes": result["data"],
            })
        except Exception as e:
            return fail(str(e), code=500)

    @bp.route("/ai/knowledge/documents/<node_id>", methods=["GET"])
    def ai_knowledge_document(node_id):
        """Get a parsed document by node ID (cache-first, then blocks API)."""
        union_id = _current_union_id()
        if not union_id:
            return fail("not logged in", code=401)

        # 1. Try cache
        cached = _cached_document(node_id)
        if cached:
            return ok(cached)

        blocked = _require_api_enabled()
        if blocked:
            return blocked

        client = DingTalkKnowledgeClient(union_id)

        # 2. Get node metadata
        detail = client.get_node_detail(node_id)
        if not detail.get("ok"):
            return fail(detail.get("error", "failed to get node"), code=detail.get("status", 502))

        meta = detail["data"]
        title = meta.get("name", "")
        ws_id = meta.get("workspaceId", "")
        category = meta.get("category", "")
        node_type = meta.get("type", "FILE")

        # 3. Get document content — only ALIDOC documents
        if category != "ALIDOC":
            return fail(f"unsupported category: {category}", code=400,
                        data={"nodeId": node_id, "title": title, "category": category})

        blocks = client.get_document_blocks(node_id)
        if not blocks.get("ok"):
            return fail(blocks.get("error", "failed to get document content"),
                        code=blocks.get("status", 502))
        else:
            parsed = parse_document(blocks["data"], "blocks")

        content = parsed["markdown"]
        _cache_document(
            node_id=node_id,
            workspace_id=ws_id,
            title=title,
            content=content,
            node_type=node_type,
            category=category,
            raw_json=json.dumps(meta, ensure_ascii=False),
        )

        return ok({
            "nodeId": node_id,
            "title": title,
            "workspaceId": ws_id,
            "content": content,
            "format": "markdown",
            "source": "api",
            "parseStatus": parsed.get("parse_status", "ok"),
        })

    @bp.route("/ai/knowledge/sync", methods=["POST"])
    def ai_knowledge_sync():
        """Walk a workspace tree and cache all documents.

        Body: { "workspace_id": "...", "check_modified": false }
        check_modified=false: 仅拉取新文档
        check_modified=true:  对比 remote_modified_at 重拉变更文档
        """
        body = request.get_json(silent=True) or {}
        workspace_id = str(body.get("workspace_id") or "").strip()
        if not workspace_id:
            return fail("missing workspace_id", code=400)

        limit = max(0, int(body.get("limit") or 0))
        check_modified = str(body.get("check_modified") or "").lower() in ("1", "true", "yes")

        union_id = str(body.get("union_id") or "").strip()
        if not union_id:
            union_id = _current_union_id()
        if not union_id:
            return fail("not logged in", code=401)

        client = DingTalkKnowledgeClient(union_id)

        # Get rootNodeId for this workspace
        ws_list = client.list_workspaces()
        root_id = ""
        ws_name = workspace_id
        if ws_list.get("ok"):
            for w in ws_list["data"]:
                if w.get("workspaceId") == workspace_id:
                    root_id = w.get("rootNodeId", "")
                    ws_name = w.get("name", workspace_id)
                    break
        if not root_id:
            return fail("cannot find rootNodeId for this workspace", code=404)

        started = time.time()
        result = _sync_workspace(client, workspace_id, root_id, limit=limit,
                                 check_modified=check_modified)
        finished = time.time()

        return ok({
            "workspaceId": workspace_id,
            "workspaceName": ws_name,
            "syncedNodes": result["syncedNodes"],
            "syncedDocs": result["syncedDocs"],
            "syncedDocIds": result["syncedDocIds"],
            "failedNodes": result["failedNodes"],
            "failedDocs": result["failedDocs"],
            "skippedWorkbooks": result.get("skippedWorkbooks", 0),
            "skippedCached": result.get("skippedCached", 0),
            "skippedUnchanged": result.get("skippedUnchanged", 0),
            "errors": result["errors"],
            "durationSec": round(finished - started, 1),
        })

    @bp.route("/ai/knowledge/sync-all", methods=["POST"])
    def ai_knowledge_sync_all():
        """Sync all known knowledge bases.

        Body: { "limit"?: N, "ws_limit"?: N, "check_modified"?: true/false }
        check_modified=false: 仅拉取新文档
        check_modified=true:  对比修改时间重拉变更文档
        """
        union_id = _current_union_id()
        if not union_id:
            return fail("not logged in", code=401)


        client = DingTalkKnowledgeClient(union_id)

        # Get all workspaces with rootNodeId
        ws_list = client.list_workspaces()
        if not ws_list.get("ok"):
            return fail("failed to list workspaces", code=502)

        body = request.get_json(silent=True) or {}
        limit = max(0, int(body.get("limit") or 0))
        ws_limit = max(0, int(body.get("ws_limit") or 0))
        check_modified = str(body.get("check_modified") or "").lower() in ("1", "true", "yes")

        from ai.knowledge.service import get_known_workspaces
        known = get_known_workspaces()

        workspaces_to_sync = [
            (w["workspaceId"], w["rootNodeId"], w["name"])
            for w in ws_list["data"]
            if w["workspaceId"] in known
        ]
        if ws_limit:
            workspaces_to_sync = workspaces_to_sync[:ws_limit]

        started = time.time()
        total_synced = 0
        total_failed = 0
        total_nodes = 0
        total_skipped_wb = 0
        total_skipped_cached = 0
        total_skipped_unchanged = 0
        results: List[dict] = []

        for ws_id, root_id, ws_name in workspaces_to_sync:
            ws_started = time.time()
            r = _sync_workspace(client, ws_id, root_id, limit=limit,
                                check_modified=check_modified)
            ws_elapsed = round(time.time() - ws_started, 1)
            results.append({
                "workspaceId": ws_id,
                "name": ws_name,
                "syncedNodes": r["syncedNodes"],
                "syncedDocs": r["syncedDocs"],
                "syncedDocIds": r["syncedDocIds"],
                "failedNodes": r["failedNodes"],
                "failedDocs": r["failedDocs"],
                "skippedWorkbooks": r.get("skippedWorkbooks", 0),
                "skippedCached": r.get("skippedCached", 0),
                "skippedUnchanged": r.get("skippedUnchanged", 0),
                "errors": r["errors"],
                "durationSec": ws_elapsed,
            })
            total_synced += r["syncedDocs"]
            total_failed += r["failedDocs"]
            total_skipped_wb += r.get("skippedWorkbooks", 0)
            total_skipped_cached += r.get("skippedCached", 0)
            total_skipped_unchanged += r.get("skippedUnchanged", 0)
            total_nodes += r["syncedNodes"]
            total_skipped_wb += r.get("skippedWorkbooks", 0)
            total_skipped_cached += r.get("skippedCached", 0)
            total_skipped_unchanged += r.get("skippedUnchanged", 0)

        finished = time.time()

        return ok({
            "syncedWorkspaces": len(results),
            "totalSynced": total_synced,
            "totalFailed": total_failed,
            "skippedWorkbooks": total_skipped_wb,
            "skippedCached": total_skipped_cached,
            "skippedUnchanged": total_skipped_unchanged,
            "workspaces": results,
            "durationSec": round(finished - started, 1),
        })

    @bp.route("/ai/knowledge/sync-and-embedding", methods=["POST"])
    def ai_knowledge_sync_and_embedding():
        """Full pipeline: sync all KBs -> rechunk -> embed.

        Body: { "check_modified"?: true/false }
        check_modified=false: KB增量（仅拉取新文档）
        check_modified=true:  KB变更（对比 modified_at 重拉变更文档）
        """
        union_id = _current_union_id()
        if not union_id:
            return fail("not logged in", code=401)

        from ai.knowledge.auto_sync import sync_all_and_embed

        body = request.get_json(silent=True) or {}
        check_modified = str(body.get("check_modified") or "").lower() in ("1", "true", "yes")

        try:
            result = sync_all_and_embed(union_id=union_id, check_modified=check_modified)
            if result.get("ok"):
                return ok(result)
            else:
                return fail(result.get("error", "full update failed"), code=500, data=result)
        except Exception as e:
            return fail(str(e), code=500)

    @bp.route("/ai/knowledge/search", methods=["POST"])
    def ai_knowledge_search():
        """Search across all accessible knowledge base documents.

        Body: { "keyword": "...", "workspace_id"? }
        """
        union_id = _current_union_id()
        if not union_id:
            return fail("not logged in", code=401)

        blocked = _require_api_enabled()
        if blocked:
            return blocked

        body = request.get_json(silent=True) or {}
        keyword = str(body.get("keyword") or body.get("q") or "").strip()
        if not keyword:
            return fail("missing keyword", code=400)

        ws_id = str(body.get("workspace_id") or "").strip()
        client = DingTalkKnowledgeClient(union_id)

        if ws_id:
            result = client.search_in_workspace(ws_id, keyword)
        else:
            result = client.search_documents(keyword)

        if not result.get("ok"):
            return fail(result.get("error", "search failed"), code=result.get("status", 502))

        return ok({"keyword": keyword, "results": result["data"]})

    @bp.route("/ai/knowledge/rechunk", methods=["POST"])
    def ai_knowledge_rechunk():
        """Re-chunk one or all documents, then auto-reembed vectors.

        Body: { "doc_id"? "all"? "embed"?: true/false }
        embed defaults to true — set false to skip vector regeneration.
        """
        body = request.get_json(silent=True) or {}
        doc_id = str(body.get("doc_id") or "").strip()
        rechunk_all = not doc_id or str(body.get("all") or "").strip().lower() in ("1", "true", "yes")
        do_embed = str(body.get("embed") or "true").strip().lower() not in ("0", "false", "no")

        from ai.knowledge.auto_sync import _rechunk_documents

        db = KbSessionLocal()
        try:
            if rechunk_all:
                docs = db.query(KbDocument).filter(KbDocument.content != "").all()
            elif doc_id:
                docs = [db.query(KbDocument).filter(KbDocument.doc_id == doc_id).first()]
                docs = [d for d in docs if d]
            else:
                return fail("missing doc_id or all=true", code=400)

            doc_ids = [d.doc_id for d in docs]
            rechunk_result = _rechunk_documents(doc_ids)
            if not rechunk_result.get("ok"):
                return fail(rechunk_result.get("error", "rechunk failed"), code=500)

            # Refresh FTS index (on kb_engine)
            from ai.knowledge.models import create_kb_fts, drop_kb_fts
            from base.db.engine import kb_engine as _kb_engine
            drop_kb_fts(_kb_engine)
            create_kb_fts(_kb_engine)

            result = {
                "chunkedDocs": rechunk_result["chunkedDocs"],
                "totalChunks": rechunk_result["totalChunks"],
            }

            # Auto-reembed: clean orphan vectors + embed new chunks
            if do_embed:
                from base.db.engine import PgVectorSessionLocal
                from sqlalchemy import text as sa_text

                # Step 1: get all valid chunk IDs from KB database
                valid_ids = [
                    r[0] for r in
                    db.execute(sa_text("SELECT id FROM kb_chunks")).fetchall()
                ]

                # Step 2: clean orphan vectors in pgvector
                pg = PgVectorSessionLocal()
                try:
                    if valid_ids:
                        placeholders = ",".join(
                            [f":id_{i}" for i in range(len(valid_ids))]
                        )
                        orphaned = pg.execute(
                            sa_text(
                                f"DELETE FROM chunk_vectors "
                                f"WHERE chunk_id NOT IN ({placeholders})"
                            ),
                            {f"id_{i}": cid for i, cid in enumerate(valid_ids)},
                        )
                    else:
                        orphaned = pg.execute(
                            sa_text("DELETE FROM chunk_vectors")
                        )
                    pg.commit()
                    result["orphanedVectors"] = orphaned.rowcount
                except Exception:
                    pg.rollback()
                finally:
                    pg.close()

                from ai.knowledge.embedder import embed_chunks
                emb_stats = embed_chunks(limit=0)
                result["embed"] = emb_stats

            return ok(result)
        except Exception as e:
            db.rollback()
            return fail(str(e), code=500)
        finally:
            db.close()

    @bp.route("/ai/knowledge/analyze/task", methods=["POST"])
    def ai_knowledge_analyze_task():
        """Fetch task data + retrieve relevant knowledge base chunks for analysis.

        Body: { "task_id": "...", "project_id"?: "..." }
        Returns task summary and knowledge base references.
        The actual multi-dimensional analysis is done by a Claude Code skill.
        """
        body = request.get_json(silent=True) or {}
        task_id = str(body.get("task_id") or "").strip()
        if not task_id:
            return fail("missing task_id", code=400)
        project_id = str(body.get("project_id") or "").strip() or None

        from base.db.orm import ProjectTask, ProjectTaskDetail
        from ai.knowledge.retriever import search_hybrid

        db = SessionLocal()
        try:
            # 1. Fetch task data
            task = db.query(ProjectTask).filter(ProjectTask.task_id == task_id).first()
            detail = None
            if project_id:
                detail = (
                    db.query(ProjectTaskDetail)
                    .filter(
                        ProjectTaskDetail.task_id == task_id,
                        ProjectTaskDetail.project_id == project_id,
                    )
                    .first()
                )
            if not detail:
                detail = (
                    db.query(ProjectTaskDetail)
                    .filter(ProjectTaskDetail.task_id == task_id)
                    .first()
                )

            if not task and not detail:
                return fail(f"task not found: {task_id}", code=404)

            # Build task summary
            task_summary = {
                "taskId": task_id,
                "title": (detail.content if detail else None) or (task.content if task else ""),
                "projectId": (detail.project_id if detail else None) or (task.project_id if task else ""),
                "priority": task.priority if task else None,
                "progress": task.progress if task else None,
                "isDone": task.is_done if task else None,
                "isOverdue": detail.is_overdue if detail else None,
                "dueDate": (detail.due_date.isoformat() if detail and detail.due_date else None)
                           or (task.due_date.isoformat() if task and task.due_date else None),
                "workHour": detail.work_hour if detail else None,
                "taskNature": detail.task_nature if detail else None,
                "businessType": detail.business_type if detail else None,
                "parentTaskId": detail.parent_task_id if detail else None,
                "executorId": task.executor_id if task else None,
                "note": task.note if task else "",
            }

            # 2. Build search query from task context
            search_text = " ".join(filter(None, [
                task_summary["title"],
                task_summary["taskNature"] or "",
                task_summary["note"],
            ]))
            if not search_text.strip():
                search_text = task_summary["title"]

            # 3. Retrieve knowledge base chunks
            chunks = []
            if search_text.strip():
                try:
                    chunks = search_hybrid(search_text, top_k=8)
                except Exception:
                    pass

            kb_references = [
                {
                    "source": c.get("title", ""),
                    "content": c.get("content", ""),
                    "score": c.get("score", 0),
                    "chunkId": c.get("chunk_id"),
                }
                for c in chunks
            ]

            return ok({
                "task": task_summary,
                "knowledge": kb_references,
                "searchQuery": search_text,
            })
        finally:
            db.close()

    @bp.route("/ai/knowledge/analyze/task/report", methods=["POST"])
    def ai_knowledge_analyze_task_report():
        """Full pipeline: fetch task + retrieve KB + LLM analysis report.

        Body: { "task_id": "..." }
        Returns structured JSON analysis report.
        """
        body = request.get_json(silent=True) or {}
        task_id = str(body.get("task_id") or "").strip()
        if not task_id:
            return fail("missing task_id", code=400)
        project_id = str(body.get("project_id") or "").strip() or None

        from base.db.orm import ProjectTask, ProjectTaskDetail
        from ai.knowledge.retriever import search_hybrid
        from ai.knowledge.analyze import analyze_task_report

        db = SessionLocal()
        try:
            # 1. Fetch task
            task = db.query(ProjectTask).filter(ProjectTask.task_id == task_id).first()
            detail = None
            if project_id:
                detail = (
                    db.query(ProjectTaskDetail)
                    .filter(
                        ProjectTaskDetail.task_id == task_id,
                        ProjectTaskDetail.project_id == project_id,
                    )
                    .first()
                )
            if not detail:
                detail = (
                    db.query(ProjectTaskDetail)
                    .filter(ProjectTaskDetail.task_id == task_id)
                    .first()
                )
            if not task and not detail:
                return fail(f"task not found: {task_id}", code=404)

            task_summary = {
                "taskId": task_id,
                "title": (detail.content if detail else None) or (task.content if task else ""),
                "projectId": (detail.project_id if detail else None) or (task.project_id if task else ""),
                "priority": task.priority if task else None,
                "progress": task.progress if task else None,
                "isDone": task.is_done if task else None,
                "isOverdue": detail.is_overdue if detail else None,
                "dueDate": (detail.due_date.isoformat() if detail and detail.due_date else None)
                           or (task.due_date.isoformat() if task and task.due_date else None),
                "workHour": detail.work_hour if detail else None,
                "taskNature": detail.task_nature if detail else None,
                "businessType": detail.business_type if detail else None,
                "parentTaskId": detail.parent_task_id if detail else None,
                "executorId": task.executor_id if task else None,
                "note": task.note if task else "",
            }

            # 2. Search KB
            search_text = " ".join(filter(None, [
                task_summary["title"],
                task_summary["taskNature"] or "",
                task_summary["note"],
            ]))
            if not search_text.strip():
                search_text = task_summary["title"]

            chunks = []
            if search_text.strip():
                try:
                    chunks = search_hybrid(search_text, top_k=8)
                except Exception:
                    pass

            kb_refs = [
                {"source": c.get("title", ""), "content": c.get("content", ""),
                 "score": c.get("score", 0), "chunkId": c.get("chunk_id")}
                for c in chunks
            ]

            # 3. Generate report
            report = analyze_task_report(task_summary, kb_refs)

            return ok({
                "task": task_summary,
                "knowledge": kb_refs,
                "report": report,
            })
        finally:
            db.close()

    @bp.route("/ai/knowledge/analyze/dashboard", methods=["POST"])
    def ai_knowledge_analyze_dashboard():
        """6-module task analysis dashboard: pull user tasks + KB + LLM.

        Body: { "owner_key"?: "...", "project_ids"?: [...], "quarter"?: "2026Q2" }
        Returns 6 analysis modules in a single response.
        """
        body = request.get_json(silent=True) or {}
        owner_key = str(body.get("owner_key") or "").strip() or None
        project_ids = body.get("project_ids") or []
        if isinstance(project_ids, list):
            project_ids = [str(p).strip() for p in project_ids if str(p).strip()]

        from base.db.orm import ProjectTask, ProjectTaskDetail
        from ai.knowledge.retriever import search_hybrid
        from ai.knowledge.dashboard_analysis import analyze_dashboard

        db = SessionLocal()
        try:
            # 1. Fetch tasks
            task_query = db.query(ProjectTask).filter(
                ProjectTask.is_deleted == False,
                ProjectTask.is_archived == False,
            )
            if project_ids:
                task_query = task_query.filter(ProjectTask.project_id.in_(project_ids))
            if owner_key:
                task_query = task_query.filter(ProjectTask.executor_id == owner_key)
            else:
                # No owner filter — return tasks across all users (admin/demo use)
                pass

            tasks = task_query.order_by(ProjectTask.priority.desc()).limit(30).all()
            if not tasks:
                return fail("no tasks found", code=404)

            task_ids = [t.task_id for t in tasks]

            # Fetch details
            details_q = db.query(ProjectTaskDetail).filter(
                ProjectTaskDetail.task_id.in_(task_ids)
            ).all()
            detail_map = {d.task_id: d for d in details_q}

            # Build task summaries
            task_summaries = []
            for t in tasks:
                d = detail_map.get(t.task_id)
                task_summaries.append({
                    "taskId": t.task_id,
                    "title": t.content or "",
                    "progress": t.progress or 0,
                    "isOverdue": d.is_overdue if d else False,
                    "isDone": t.is_done,
                    "workHour": d.work_hour if d else None,
                    "taskNature": d.task_nature if d else None,
                    "businessType": d.business_type if d else None,
                    "dueDate": d.due_date.isoformat() if d and d.due_date else (t.due_date.isoformat() if t and t.due_date else None),
                })

            # 2. Work hour stats (assigned/autonomous/capability)
            work_types: Dict[str, int] = {"指派型": 0, "自主型": 0, "能力型": 0, "其他": 0}
            done_count = 0
            overdue_count = 0
            total_work_hours = 0.0
            for t in tasks:
                d = detail_map.get(t.task_id)
                if t.is_done:
                    done_count += 1
                if d and d.is_overdue:
                    overdue_count += 1
                wh = d.work_hour if d else None
                if wh:
                    total_work_hours += wh
                nature = (d.task_nature if d else None) or "其他"
                found = False
                for key in work_types:
                    if key in str(nature):
                        work_types[key] += 1
                        found = True
                        break
                if not found:
                    work_types["其他"] += 1

            total = len(tasks)
            work_hour_stats = {
                "total_tasks": total,
                "done_count": done_count,
                "overdue_count": overdue_count,
                "total_work_hours": round(total_work_hours, 1),
                "assigned_pct": round(work_types.get("指派型", 0) / max(total, 1) * 100, 1),
                "autonomous_pct": round(work_types.get("自主型", 0) / max(total, 1) * 100, 1),
                "capability_pct": round(work_types.get("能力型", 0) / max(total, 1) * 100, 1),
            }

            # 3. Search KB with combined task keywords
            search_text = " ".join([t.get("title", "") for t in task_summaries[:5]])
            kb_chunks = []
            if search_text.strip():
                try:
                    kb_chunks = search_hybrid(search_text, top_k=8)
                except Exception:
                    pass
            kb_refs = [
                {"source": c.get("title", ""), "content": c.get("content", ""),
                 "score": c.get("score", 0)} for c in kb_chunks
            ]

            # 4. Run analysis
            modules = analyze_dashboard(task_summaries, work_hour_stats, kb_refs)

            if "error" in modules:
                return fail(modules["error"], code=502, data={"raw": modules.get("raw", "")})

            return ok({
                "modules": modules,
                "meta": {
                    "taskCount": total,
                    "analyzedAt": datetime.now(timezone.utc).isoformat(),
                },
            })
        finally:
            db.close()

    @bp.route("/ai/knowledge/chat/session", methods=["POST"])
    def ai_knowledge_chat_session():
        """Create a new chat session, return session_id."""
        from ai.knowledge.chat_session import create_session
        sid = create_session()
        return ok({"sessionId": sid})

    @bp.route("/ai/knowledge/chat", methods=["GET"])
    def ai_knowledge_chat():
        """SSE knowledge-base chat endpoint.

        Query params: q (question), session_id (optional), workspace_id (optional).
        Returns text/event-stream with message and done events.
        """
        q = str(request.args.get("q") or "").strip()
        if not q:
            return fail("missing q", code=400)
        session_id = str(request.args.get("session_id") or "").strip()
        ws_id = str(request.args.get("workspace_id") or "").strip() or None

        from flask import Response, stream_with_context
        from ai.knowledge.chat import chat_stream

        return Response(
            stream_with_context(chat_stream(q, session_id=session_id, workspace_id=ws_id)),
            mimetype="text/event-stream; charset=utf-8",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    @bp.route("/ai/knowledge/chunks/search", methods=["POST"])
    def ai_knowledge_chunks_search():
        """Local search on kb_chunks (keyword / vector / hybrid).

        Body: { "query": "...", "top_k": 10, "workspace_id": "...", "method": "hybrid" }
        method: "keyword" (FULLTEXT), "vector" (cosine), "hybrid" (RRF fusion, default)
        """
        body = request.get_json(silent=True) or {}
        query = str(body.get("query") or body.get("q") or "").strip()
        if not query:
            return fail("missing query", code=400)

        top_k = max(1, min(50, int(body.get("top_k") or 10)))
        ws_id = str(body.get("workspace_id") or "").strip() or None
        method = str(body.get("method") or "hybrid").strip().lower()

        from ai.knowledge.retriever import search_chunks, search_hybrid, search_vector

        try:
            if method == "keyword":
                chunks = search_chunks(query, top_k=top_k, workspace_id=ws_id)
            elif method == "vector":
                chunks = search_vector(query, top_k=top_k, workspace_id=ws_id)
            else:
                chunks = search_hybrid(query, top_k=top_k, workspace_id=ws_id)
            return ok({"query": query, "method": method, "total": len(chunks), "chunks": chunks})
        except Exception as e:
            return fail(str(e), code=500)

    @bp.route("/ai/knowledge/reembed", methods=["POST"])
    def ai_knowledge_reembed():
        """Embed kb_chunks into pgvector chunk_vectors for semantic search.

        Body: { "workspace_id"?: "...", "limit"?: N }
        """
        body = request.get_json(silent=True) or {}
        ws_id = str(body.get("workspace_id") or "").strip() or None
        limit = max(0, int(body.get("limit") or 0))

        from ai.knowledge.embedder import embed_chunks

        try:
            stats = embed_chunks(workspace_id=ws_id, limit=limit)
            return ok(stats)
        except Exception as e:
            return fail(str(e), code=500)

    @bp.route("/ai/knowledge/documents/fill-markdown", methods=["POST"])
    def ai_knowledge_fill_markdown():
        """将 MCP 下载的 markdown 文件回填到 kb_documents.raw_json。

        Body: { "markdown_dir": "/path/to/markdown" }
        递归扫描目录下所有 {node_id}.md 文件（由 dingtalk-download-by-nodes.py 生成）。

        行为：
        - 递归扫描目录下所有 .md 文件
        - 按文件名（node_id）匹配 kb_documents 记录
        - 将 markdown 内容写入 raw_json 字段
        - 跳过非 node_id 格式的 .md 文件（如 _download_summary.md）
        """
        body = request.get_json(silent=True) or {}
        md_dir = str(body.get("markdown_dir") or "").strip()
        if not md_dir:
            return fail("missing markdown_dir", code=400)

        from pathlib import Path
        p = Path(md_dir)
        if not p.is_dir():
            return fail(f"markdown_dir not found: {md_dir}", code=404)

        # 递归收集所有 .md 文件，跳过以下划线开头的摘要文件
        md_files = sorted(
            f for f in p.rglob("*.md")
            if not f.name.startswith("_")
        )
        if not md_files:
            return ok({"filled": 0, "skipped": 0, "errors": 0, "message": "no .md files found"})

        db = KbSessionLocal()
        now = datetime.now(timezone.utc)
        filled = 0
        skipped = 0
        errors = 0

        try:
            for f in md_files:
                node_id = f.stem  # 文件名去掉 .md 即为 node_id
                try:
                    content = f.read_text(encoding="utf-8")
                except Exception as e:
                    errors += 1
                    print(f"[fill-markdown] read error {f}: {e}")
                    continue

                row = db.query(KbDocument).filter(KbDocument.node_id == node_id).first()
                if not row:
                    skipped += 1
                    continue

                row.raw_json = content
                row.updated_at = now
                filled += 1

            db.commit()
        except Exception as e:
            db.rollback()
            return fail(str(e), code=500)
        finally:
            db.close()

        return ok({
            "filled": filled,
            "skipped": skipped,
            "errors": errors,
            "total_files": len(md_files),
            "markdown_dir": md_dir,
        })
