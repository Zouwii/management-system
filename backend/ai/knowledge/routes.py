"""HTTP routes for knowledge base document browsing and downloading.

Endpoints:
  GET  /ai/knowledge/workspaces                    - List knowledge bases (sorted by priority)
  GET  /ai/knowledge/workspaces/<ws_id>/nodes      - Browse document tree
  GET  /ai/knowledge/documents/<node_id>           - Get parsed document content (blocks → markdown)
  POST /ai/knowledge/sync                          - Walk tree and cache all documents
  POST /ai/knowledge/search                        - Full-text search across knowledge bases
  POST /ai/knowledge/ttyd/session                  - Create/reuse a knowledge-base Q&A ttyd session
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, List

from flask import request, session

from ai.knowledge.models import KbDocument, KbChunk
from ai.knowledge.parser import parse_document
from ai.knowledge.service import DingTalkKnowledgeClient, sort_workspaces
from ai.terminal.session import (
    build_ttyd_embed_url,
    ensure_ttyd_session,
    owner_ttyd_port,
    resolve_owner_key,
    resolve_owner_name,
    user_workspace,
)
from db.engine import SessionLocal


# ── helpers ────────────────────────────────────────────────────

def _current_union_id() -> str:
    """优先从 session 获取用户，失败回退到 DB fallback。"""
    auth = session.get("auth_user") or {}
    user_id = ""
    if isinstance(auth, dict):
        user_id = str(auth.get("user_id") or "")
    if user_id:
        try:
            from db.orm import UserCharacter as DbUserCharacter
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
        from db.orm import UserCharacter as DbUserCharacter
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

def _cache_document(node_id: str, workspace_id: str, title: str,
                    content: str, node_type: str = "FILE",
                    parent_id: str = "", raw_json: str = "",
                    category: str = "") -> None:
    db = SessionLocal()
    try:
        existing = db.query(KbDocument).filter(KbDocument.doc_id == node_id).first()
        now = datetime.now(timezone.utc)
        if existing:
            existing.title = title
            existing.content = content
            existing.node_type = node_type
            existing.parent_id = parent_id
            existing.workspace_id = workspace_id
            existing.raw_json = raw_json
            existing.synced_at = now
            existing.updated_at = now
        else:
            db.add(KbDocument(
                doc_id=node_id,
                workspace_id=workspace_id,
                title=title,
                node_type=node_type,
                parent_id=parent_id,
                content=content,
                raw_json=raw_json,
                synced_at=now,
                created_at=now,
                updated_at=now,
            ))
        db.commit()
    finally:
        db.close()


def _cached_document(node_id: str) -> dict | None:
    db = SessionLocal()
    try:
        row = db.query(KbDocument).filter(KbDocument.doc_id == node_id).first()
        if row and row.content:
            return {
                "nodeId": row.doc_id,
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


# ── route registration ─────────────────────────────────────────

def register(bp, ok, fail):

    @bp.route("/ai/knowledge/workspaces", methods=["GET"])
    def ai_knowledge_workspaces():
        """List knowledge bases accessible to the current user, sorted by priority."""
        union_id = _current_union_id()
        if not union_id:
            return fail("not logged in — unable to determine user identity", code=401)

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

        # 3. Get document content
        blocks = client.get_document_blocks(node_id)
        if not blocks.get("ok"):
            # Try workbook
            sheets_result = client.get_workbook_sheets(node_id)
            if sheets_result.get("ok"):
                sheets_data = []
                for s in sheets_result["data"]:
                    sid = s.get("id", "")
                    sname = s.get("name", "")
                    ranges = client.get_workbook_range(node_id, sid)
                    rows = ranges.get("data", []) if ranges.get("ok") else []
                    sheets_data.append((sname, rows))
                parsed = parse_document(sheets_data, "workbook")
            else:
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

    def _sync_workspace(client, workspace_id: str, root_id: str, limit: int = 0) -> dict:
        """Walk a workspace tree, cache all documents. Returns {syncedCount, failedCount, errors}."""
        synced: List[str] = []
        errors: List[dict] = []

        def _walk(parent_id: str):
            if limit and len(synced) >= limit:
                return
            result = client.list_nodes(workspace_id, parent_id)
            if not result.get("ok"):
                errors.append({"parentId": parent_id, "error": result.get("error", "")})
                return

            for n in result["data"]:
                if limit and len(synced) >= limit:
                    return
                nid = n["nodeId"]
                ntype = n["type"]
                title = n["name"]

                if ntype == "FOLDER":
                    _walk(nid)
                elif ntype == "FILE":
                    try:
                        meta = client.get_node_detail(nid)
                        if not meta.get("ok"):
                            errors.append({"nodeId": nid, "title": title, "error": "metadata failed"})
                            continue

                        blocks = client.get_document_blocks(nid)
                        if blocks.get("ok"):
                            parsed = parse_document(blocks["data"], "blocks")
                        else:
                            sheets_result = client.get_workbook_sheets(nid)
                            if sheets_result.get("ok"):
                                sheets_data = []
                                for s in sheets_result["data"]:
                                    sid = s.get("id", "")
                                    sname = s.get("name", "")
                                    rng = client.get_workbook_range(nid, sid)
                                    rows = rng.get("data", []) if rng.get("ok") else []
                                    sheets_data.append((sname, rows))
                                parsed = parse_document(sheets_data, "workbook")
                            else:
                                errors.append({"nodeId": nid, "title": title, "error": "content failed"})
                                continue

                        _cache_document(
                            node_id=nid,
                            workspace_id=workspace_id,
                            title=title,
                            content=parsed["markdown"],
                            node_type="FILE",
                            parent_id=parent_id or "",
                            category=n.get("category", ""),
                            raw_json=json.dumps(n, ensure_ascii=False),
                        )
                        synced.append(nid)
                    except Exception as e:
                        errors.append({"nodeId": nid, "title": title, "error": str(e)})

        _walk(root_id)
        return {
            "syncedCount": len(synced),
            "failedCount": len(errors),
            "errors": errors[:20],
        }

    @bp.route("/ai/knowledge/sync", methods=["POST"])
    def ai_knowledge_sync():
        """Walk a workspace tree and cache all documents.

        Body: { "workspace_id": "..." }
        """
        union_id = _current_union_id()
        if not union_id:
            return fail("not logged in", code=401)

        body = request.get_json(silent=True) or {}
        workspace_id = str(body.get("workspace_id") or "").strip()
        if not workspace_id:
            return fail("missing workspace_id", code=400)

        limit = max(0, int(body.get("limit") or 0))  # 0 = no limit

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
        result = _sync_workspace(client, workspace_id, root_id, limit=limit)
        finished = time.time()

        return ok({
            "workspaceId": workspace_id,
            "workspaceName": ws_name,
            "syncedCount": result["syncedCount"],
            "failedCount": result["failedCount"],
            "errors": result["errors"],
            "durationSec": round(finished - started, 1),
        })

    @bp.route("/ai/knowledge/sync-all", methods=["POST"])
    def ai_knowledge_sync_all():
        """Sync all known knowledge bases, then optionally rechunk.

        Body: { "rechunk": true/false }  (default: false)
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
        rechunk_flag = str(body.get("rechunk") or "").strip().lower() in ("1", "true", "yes")
        limit = max(0, int(body.get("limit") or 0))  # 0 = no limit
        ws_limit = max(0, int(body.get("ws_limit") or 0))  # 0 = all workspaces

        from ai.knowledge.service import KNOWN_WORKSPACES

        workspaces_to_sync = [
            (w["workspaceId"], w["rootNodeId"], w["name"])
            for w in ws_list["data"]
            if w["workspaceId"] in KNOWN_WORKSPACES
        ]
        if ws_limit:
            workspaces_to_sync = workspaces_to_sync[:ws_limit]

        started = time.time()
        total_synced = 0
        total_failed = 0
        results: List[dict] = []

        for ws_id, root_id, ws_name in workspaces_to_sync:
            ws_started = time.time()
            r = _sync_workspace(client, ws_id, root_id, limit=limit)
            ws_elapsed = round(time.time() - ws_started, 1)
            results.append({
                "workspaceId": ws_id,
                "name": ws_name,
                "syncedCount": r["syncedCount"],
                "failedCount": r["failedCount"],
                "errors": r["errors"],
                "durationSec": ws_elapsed,
            })
            total_synced += r["syncedCount"]
            total_failed += r["failedCount"]

        finished = time.time()

        # Auto-rechunk if requested
        rechunk_result = None
        if rechunk_flag:
            from ai.knowledge.chunker import chunk_document
            from ai.knowledge.models import create_kb_fts, drop_kb_fts
            from db.engine import engine as _engine

            db = SessionLocal()
            try:
                total_chunks = 0
                docs = db.query(KbDocument).filter(KbDocument.content != "").all()
                for doc in docs:
                    db.query(KbChunk).filter(KbChunk.doc_id == doc.doc_id).delete()
                    chunks = chunk_document(doc.doc_id, doc.title, doc.content, doc.node_type)
                    for c in chunks:
                        db.add(KbChunk(
                            doc_id=c["doc_id"],
                            chunk_index=c["chunk_index"],
                            content=c["content"],
                            token_count=c["token_count"],
                        ))
                    total_chunks += len(chunks)
                db.commit()
                drop_kb_fts(_engine)
                create_kb_fts(_engine)
                rechunk_result = {"chunkedDocs": len(docs), "totalChunks": total_chunks}
            except Exception as e:
                db.rollback()
                rechunk_result = {"error": str(e)}
            finally:
                db.close()

        return ok({
            "syncedWorkspaces": len(results),
            "totalSynced": total_synced,
            "totalFailed": total_failed,
            "workspaces": results,
            "rechunk": rechunk_result,
            "durationSec": round(finished - started, 1),
        })

    @bp.route("/ai/knowledge/search", methods=["POST"])
    def ai_knowledge_search():
        """Search across all accessible knowledge base documents.

        Body: { "keyword": "...", "workspace_id"? }
        """
        union_id = _current_union_id()
        if not union_id:
            return fail("not logged in", code=401)

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
        """Re-chunk one or all documents into kb_chunks.

        Body: { "doc_id"? "all"? }
        """
        body = request.get_json(silent=True) or {}
        doc_id = str(body.get("doc_id") or "").strip()
        rechunk_all = not doc_id or str(body.get("all") or "").strip().lower() in ("1", "true", "yes")

        from ai.knowledge.chunker import chunk_document

        db = SessionLocal()
        try:
            if rechunk_all:
                docs = db.query(KbDocument).filter(KbDocument.content != "").all()
            elif doc_id:
                docs = [db.query(KbDocument).filter(KbDocument.doc_id == doc_id).first()]
                docs = [d for d in docs if d]
            else:
                return fail("missing doc_id or all=true", code=400)

            total_chunks = 0
            for doc in docs:
                # Delete old chunks
                db.query(KbChunk).filter(KbChunk.doc_id == doc.doc_id).delete()
                chunks = chunk_document(doc.doc_id, doc.title, doc.content, doc.node_type)
                for c in chunks:
                    db.add(KbChunk(
                        doc_id=c["doc_id"],
                        chunk_index=c["chunk_index"],
                        content=c["content"],
                        token_count=c["token_count"],
                    ))
                total_chunks += len(chunks)

            db.commit()

            # Refresh FTS index
            from ai.knowledge.models import create_kb_fts, drop_kb_fts
            from db.engine import engine as _engine
            drop_kb_fts(_engine)
            create_kb_fts(_engine)

            return ok({
                "chunkedDocs": len(docs),
                "totalChunks": total_chunks,
            })
        except Exception as e:
            db.rollback()
            return fail(str(e), code=500)
        finally:
            db.close()

    @bp.route("/ai/knowledge/ttyd/session", methods=["POST"])
    def ai_knowledge_ttyd_session():
        """Create or reuse a knowledge-base Q&A ttyd session.

        Uses '{ownerKey}__kb' as the session key to avoid conflicting with
        the tbcreate ttyd session (which uses '{ownerKey}').

        Request body (optional): {"ownerKey": "...", "model": "..."}
        Returns embedUrl, ownerKey, model, port, pid.
        """
        payload = request.get_json(silent=True) or {}
        auth_user = session.get("auth_user") or {}
        base_owner_key = resolve_owner_key(payload, auth_user)
        owner_name = resolve_owner_name(auth_user)

        # Use a dedicated session key to isolate from tbcreate ttyd
        owner_key = f"{base_owner_key}__kb"
        cfg = {}
        try:
            from ai.terminal.session import load_ai_config
            cfg = load_ai_config()
        except Exception:
            pass
        model = str(payload.get("model") or cfg.get("model") or "glm-5.1").strip() or "glm-5.1"

        # Init knowledge workspace context before starting ttyd
        try:
            from ai.knowledge.workspace import init_knowledge_workspace
            init_knowledge_workspace(owner_key)
        except Exception:
            pass

        try:
            state = ensure_ttyd_session(
                owner_key=owner_key, owner_name=owner_name, model=model,
                auth_user=auth_user, skill="",
            )
        except Exception as exc:
            return fail(str(exc), code=500, data={})

        ws = user_workspace(owner_key)
        embed_url = build_ttyd_embed_url(
            port=int(state.get("port") or owner_ttyd_port(owner_key)),
            owner_key=owner_key,
            model=model,
            skill="",
        )
        return ok({
            "embedUrl": embed_url,
            "ownerKey": owner_key,
            "ownerSafe": ws["owner_safe"],
            "userRoot": ws["user_root"],
            "workspaceDir": ws["workspace_dir"],
            "model": model,
            "port": int(state.get("port") or 0),
            "pid": int(state.get("proc").pid) if state.get("proc") else 0,
        })

    @bp.route("/ai/knowledge/chunks/search", methods=["POST"])
    def ai_knowledge_chunks_search():
        """Local full-text search on kb_chunks.

        Body: { "query": "...", "top_k": 10, "workspace_id": "..." }
        """
        body = request.get_json(silent=True) or {}
        query = str(body.get("query") or body.get("q") or "").strip()
        if not query:
            return fail("missing query", code=400)

        top_k = max(1, min(50, int(body.get("top_k") or 10)))
        ws_id = str(body.get("workspace_id") or "").strip() or None

        from ai.knowledge.retriever import search_chunks

        try:
            chunks = search_chunks(query, top_k=top_k, workspace_id=ws_id)
            return ok({"query": query, "total": len(chunks), "chunks": chunks})
        except Exception as e:
            return fail(str(e), code=500)

