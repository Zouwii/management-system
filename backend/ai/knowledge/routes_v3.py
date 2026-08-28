"""RAG v3 pipeline endpoints — no circular imports."""
from __future__ import annotations

import json
import os as _os
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from flask import request

from ai.knowledge.markdown_sync import _download_one
from ai.knowledge.models import KbDocument, KbNode, KbChunk
from ai.knowledge.service import DingTalkKnowledgeClient
from ai.knowledge.cleaner import clean_markdown
from base.db.engine import KbSessionLocal


def register_v3(bp, ok, fail):
    """Register all v3 pipeline endpoints on the given blueprint."""

    # ── helpers inside closure ──────────────────────────────────

    def _current_uid():
        from base.db.orm import UserCharacter
        from base.db.engine import SessionLocal
        db = SessionLocal()
        try:
            row = db.query(UserCharacter).filter(
                UserCharacter.union_id.isnot(None), UserCharacter.union_id != "").first()
            return row.union_id if row else ""
        finally:
            db.close()

    def _ws_name_map():
        """Load workspace_id -> Chinese name mapping from kb_workspaces.json.
        Cached in closure to avoid repeated file reads.
        """
        if not hasattr(_ws_name_map, "_cache"):
            import json as _json
            cfg_path = Path(__file__).resolve().parent.parent.parent / "base" / "kb_workspaces.json"
            try:
                cfg = _json.loads(cfg_path.read_text(encoding="utf-8"))
                _ws_name_map._cache = {}
                for name, info in cfg.get("kb_workspaces", {}).items():
                    wid = info.get("workspace_id", "")
                    if wid:
                        _ws_name_map._cache[wid] = name
            except Exception:
                _ws_name_map._cache = {}
        return _ws_name_map._cache

    def _build_md_path(ws, doc_title, breadcrumb, md_root, parent_dir=None):
        """Build markdown file path from breadcrumb and document info.

        breadcrumb format: "ws_id / dir1 / dir2 / ... / filename.adoc"
        parent_dir: optional override for the root download directory

        Uses kb_workspaces.json to map workspace_id -> disk root dir name.
        Falls back to filename search under md_root if exact path not found.
        """
        parts = [p.strip() for p in (breadcrumb or "").split(" / ") if p.strip()]

        # Replace workspace_id with Chinese workspace name for disk path
        ws_name = _ws_name_map().get(ws, ws)
        if parts and parts[0] == ws:
            parts[0] = ws_name

        # Remove last part if it looks like the document filename
        if parts:
            last = parts[-1]
            title_base = doc_title.rsplit(".", 1)[0] if "." in doc_title else doc_title
            last_base = last.rsplit(".", 1)[0] if "." in last else last
            if last_base == title_base or last == doc_title:
                parts.pop()

        # Build filename
        fn = re.sub(r'[\\/:*?"<>|]', '-', doc_title)
        fn = fn.rsplit(".", 1)[0] + ".md"

        root = parent_dir or md_root
        fp = Path(root) / Path(*parts) / fn

        # Fallback: search by filename under md_root if exact path doesn't exist
        if not fp.exists() and not parent_dir:
            try:
                found = list(Path(md_root).rglob(fn))
                if found:
                    return found[0]  # use first match
            except Exception:
                pass

        return fp

    def _extract_outline(markdown):
        # Import from routes to avoid circular — defined at module-level in routes.py
        from ai.knowledge.routes import _extract_outline_v2
        return _extract_outline_v2(markdown)

    def _sync_meta(workspace_id, union_id, check_modified=False):
        from ai.knowledge.routes import _sync_workspace
        client = DingTalkKnowledgeClient(union_id)
        wl = client.list_workspaces()
        root_id = ""
        for w in wl.get("data", []):
            if w.get("workspaceId") == workspace_id:
                root_id = w.get("rootNodeId", "")
                break
        if not root_id:
            return None
        return _sync_workspace(client, workspace_id, root_id, check_modified=check_modified)

    def _do_download(ws, md_root, mcp_url, w, node_ids=None, parent_dir=None):
        db = KbSessionLocal()
        try:
            q = db.query(KbDocument).filter(KbDocument.workspace_id == ws,
                KbDocument.fetch_status.in_(["pending", "downloading"]))
            if node_ids:
                q = q.filter(KbDocument.node_id.in_([str(n) for n in node_ids]))
            pending = q.all()
            nids = [d.node_id for d in pending]
            nodes = db.query(KbNode).filter(KbNode.node_id.in_(nids)).all() if nids else []
            nmap = {n.node_id: n for n in nodes}
        finally:
            db.close()
        d_ok, d_skip, d_fail = 0, 0, 0
        lock = threading.Lock(); now = datetime.now(timezone.utc)
        def _dl(doc):
            nonlocal d_ok, d_skip, d_fail
            try:
                node = nmap.get(doc.node_id)
                bc = node.breadcrumb if node else ""
                fp = _build_md_path(ws, doc.title, bc, md_root, parent_dir)
                if fp.exists():
                    db2 = KbSessionLocal()
                    try:
                        r = db2.query(KbDocument).filter(KbDocument.node_id == doc.node_id).first()
                        if r and r.fetch_status != "success":
                            r.fetch_status = "downloaded"; r.updated_at = now
                        db2.commit()
                    except Exception: db2.rollback()
                    finally: db2.close()
                    with lock: d_skip += 1
                    return
                dl = _download_one({"node_id": doc.node_id, "title": doc.title}, mcp_url, timeout=60)
                if not dl.get("ok"):
                    with lock: d_fail += 1; return
                fp.parent.mkdir(parents=True, exist_ok=True)
                fp.write_text(dl["markdown"], encoding="utf-8")
                db2 = KbSessionLocal()
                try:
                    r = db2.query(KbDocument).filter(KbDocument.node_id == doc.node_id).first()
                    if r: r.fetch_status = "downloaded"; r.synced_at = now; r.updated_at = now
                    db2.commit()
                except Exception: db2.rollback()
                finally: db2.close()
                with lock: d_ok += 1
            except Exception:
                with lock: d_fail += 1
        if pending:
            with ThreadPoolExecutor(max_workers=w) as ex:
                list(ex.map(_dl, pending))
        return {"pending": len(pending), "downloaded": d_ok, "skipped": d_skip, "failed": d_fail, "md_root": md_root}

    def _do_import(ws, md_root, w, parent_dir=None):
        db = KbSessionLocal()
        try:
            docs = db.query(KbDocument).filter(KbDocument.workspace_id == ws,
                KbDocument.fetch_status == "downloaded").all()
            nids = [d.node_id for d in docs]
            nodes = db.query(KbNode).filter(KbNode.node_id.in_(nids)).all() if nids else []
            nmap = {n.node_id: n for n in nodes}
        finally: db.close()
        st = {"scanned": len(docs), "ok": 0, "no_file": 0, "error": 0}
        lock = threading.Lock(); now = datetime.now(timezone.utc)
        def _imp(doc):
            try:
                node = nmap.get(doc.node_id)
                bc = node.breadcrumb if node else ""
                fp = _build_md_path(ws, doc.title, bc, md_root, parent_dir)
                if not fp.exists():
                    with lock: st["no_file"] += 1; return
                raw = fp.read_text(encoding="utf-8")
                cr = clean_markdown(raw, doc.title)
                cleaned = cr.cleaned_md
                outline = _extract_outline(cleaned)
                db2 = KbSessionLocal()
                try:
                    r = db2.query(KbDocument).filter(KbDocument.node_id == doc.node_id).first()
                    if r:
                        r.content = cleaned
                        r.outline = json.dumps(outline, ensure_ascii=False)
                        r.fetch_status = "success"; r.updated_at = now
                    db2.commit()
                except Exception: db2.rollback()
                finally: db2.close()
                with lock: st["ok"] += 1
            except Exception:
                with lock: st["error"] += 1
        if docs:
            with ThreadPoolExecutor(max_workers=w) as ex:
                list(ex.map(_imp, docs))
        return st

    def _do_index(ws, w):
        """Index documents: chunk + embed.

        1. Query documents with fetch_status='success' + non-empty content
        2. Delete old chunks for those docs
        3. Chunk each doc (leaf + parent)
        4. Insert leaf chunks first, get DB IDs
        5. Insert parent chunks, link leaf chunks via parent_id
        6. Embed leaf chunks (depth=1 only)
        """
        from ai.knowledge.chunk_strategy import chunk_document_for_index
        from ai.knowledge.chunk_storage import persist_chunk_result
        from ai.knowledge.embedder import embed_chunks, delete_vectors

        db = KbSessionLocal()
        try:
            q = db.query(KbDocument).filter(
                KbDocument.workspace_id == ws,
                KbDocument.fetch_status == "success",
                KbDocument.content.isnot(None),
                KbDocument.content != "",
            )
            docs = q.all()
        finally:
            db.close()

        if not docs:
            return {"status": "no documents to index", "workspace_id": ws}

        stats = {"docs": len(docs), "leaf_chunks": 0, "parent_chunks": 0,
                 "chunk_errors": 0, "embedded": 0, "embed_errors": 0}

        for doc in docs:
            db = KbSessionLocal()
            try:
                # Delete old chunks for this doc
                old_ids = [r[0] for r in db.query(KbChunk.id).filter(
                    KbChunk.doc_id == doc.node_id
                ).all()]
                db.query(KbChunk).filter(KbChunk.doc_id == doc.node_id).delete()
                db.commit()

                # Delete old vectors
                if old_ids:
                    delete_vectors(old_ids)

                # Chunk
                node = db.query(KbNode.breadcrumb).filter(
                    KbNode.node_id == doc.node_id
                ).first()
                result = chunk_document_for_index(
                    doc.node_id, doc.title, doc.content,
                    doc.outline or "", "FILE",
                    node[0] if node else "",
                )
                persisted = persist_chunk_result(db, result)

                db.commit()
                stats["leaf_chunks"] += persisted["leaf_count"]
                stats["parent_chunks"] += persisted["parent_count"]

            except Exception:
                db.rollback()
                stats["chunk_errors"] += 1
            finally:
                db.close()

        # Embed leaf chunks only
        if stats["leaf_chunks"] > 0:
            try:
                emb_result = embed_chunks(workspace_id=ws, depth=1)
                stats["embedded"] = emb_result.get("embedded", 0)
                stats["embed_errors"] = emb_result.get("errors", 0)
            except Exception:
                stats["embed_errors"] = -1  # signal failure

        return stats

    # ── endpoints ───────────────────────────────────────────────

    @bp.route("/ai/knowledge/v3/sync", methods=["POST"])
    def v3_sync():
        body = request.get_json(silent=True) or {}
        ws = str(body.get("workspace_id") or "").strip()
        if not ws: return fail("missing workspace_id", code=400)
        steps = body.get("steps") or ["meta", "download", "import", "index"]
        w = max(1, min(16, int(body.get("workers") or 5)))
        md_root = str(body.get("markdown_root") or _os.getenv("V3_MARKDOWN_ROOT", "/home/jz/zhr/markdown")).strip()
        uid = str(body.get("union_id") or "").strip() or _current_uid()
        if not uid: return fail("not logged in", code=401)
        mcp_url = str(_os.getenv("DINGTALK_KB_MCP_URL") or "").strip()

        result = {"workspace_id": ws, "steps": {}}
        if "meta" in steps:
            meta = _sync_meta(ws, uid)
            if meta is None: return fail("cannot find rootNodeId", code=404)
            result["steps"]["meta"] = {"nodes": meta["syncedNodes"], "docs": meta["syncedDocs"]}
        if "download" in steps:
            if not mcp_url: result["steps"]["download"] = {"error": "missing DINGTALK_KB_MCP_URL"}
            else:
                parent_dir = str(body.get("parent_dir") or "").strip() or None
                result["steps"]["download"] = _do_download(ws, md_root, mcp_url, w, parent_dir=parent_dir)
        if "import" in steps:
            parent_dir = str(body.get("parent_dir") or "").strip() or None
            result["steps"]["import"] = _do_import(ws, md_root, w, parent_dir=parent_dir)
        if "index" in steps:
            result["steps"]["index"] = _do_index(ws, w)
        return ok(result)

    @bp.route("/ai/knowledge/v3/download", methods=["POST"])
    def v3_download():
        body = request.get_json(silent=True) or {}
        ws = str(body.get("workspace_id") or "").strip()
        if not ws: return fail("missing workspace_id", code=400)
        md_root = str(body.get("markdown_root") or _os.getenv("V3_MARKDOWN_ROOT", "/home/jz/zhr/markdown")).strip()
        w = max(1, min(16, int(body.get("workers") or 5)))
        nids = body.get("node_ids") or []
        parent_dir = str(body.get("parent_dir") or "").strip() or None
        mcp_url = str(_os.getenv("DINGTALK_KB_MCP_URL") or "").strip()
        if not mcp_url: return fail("missing DINGTALK_KB_MCP_URL", code=500)
        return ok(_do_download(ws, md_root, mcp_url, w, node_ids=nids, parent_dir=parent_dir))

    @bp.route("/ai/knowledge/v3/import", methods=["POST"])
    def v3_import():
        body = request.get_json(silent=True) or {}
        ws = str(body.get("workspace_id") or "").strip()
        if not ws: return fail("missing workspace_id", code=400)
        md_root = str(body.get("markdown_root") or _os.getenv("V3_MARKDOWN_ROOT", "/home/jz/zhr/markdown")).strip()
        w = max(1, min(16, int(body.get("workers") or 5)))
        parent_dir = str(body.get("parent_dir") or "").strip() or None
        return ok(_do_import(ws, md_root, w, parent_dir=parent_dir))

    @bp.route("/ai/knowledge/v3/index", methods=["POST"])
    def v3_index():
        body = request.get_json(silent=True) or {}
        ws = str(body.get("workspace_id") or "").strip() or None
        w = max(1, min(16, int(body.get("workers") or 5)))
        return ok(_do_index(ws, w))

    @bp.route("/ai/knowledge/v3/status", methods=["GET"])
    def v3_status():
        db = KbSessionLocal()
        try:
            total = db.query(KbDocument).count()
            hc = db.query(KbDocument).filter(KbDocument.content.isnot(None), KbDocument.content != "").count()
            ho = db.query(KbDocument).filter(KbDocument.outline.isnot(None), KbDocument.outline != "", KbDocument.outline != "[]").count()
            ct = db.query(KbChunk).count()
            cl = db.query(KbChunk).filter(KbChunk.depth == 1).count()
        finally: db.close()
        vc = 0
        try:
            from base.db.engine import PgVectorSessionLocal
            from sqlalchemy import text as sa_text
            pg = PgVectorSessionLocal()
            try: vc = pg.execute(sa_text("SELECT COUNT(*) FROM chunk_vectors")).scalar() or 0
            finally: pg.close()
        except Exception: pass
        return ok({"kb_documents": {"total": total, "has_content": hc, "has_outline": ho},
                    "kb_chunks": {"total": ct, "leaf": cl}, "pgvector": {"chunk_vectors": vc}})

    @bp.route("/ai/knowledge/v3/search", methods=["POST"])
    def v3_search():
        """V3 retrieval: leaf search → parent + sibling expansion."""
        body = request.get_json(silent=True) or {}
        query = str(body.get("query") or "").strip()
        if not query:
            return fail("missing query", code=400)
        top_k = max(1, min(50, int(body.get("top_k") or 10)))
        ws = str(body.get("workspace_id") or "").strip() or None
        expand_parents = body.get("expand_parents", True)
        expand_siblings = body.get("expand_siblings", True)
        sibling_radius = max(0, min(3, int(body.get("sibling_radius") or 1)))

        from ai.knowledge.retriever import search_v3
        result = search_v3(
            query, top_k=top_k, workspace_id=ws,
            expand_parents=expand_parents,
            expand_siblings=expand_siblings,
            sibling_radius=sibling_radius,
        )
        return ok(result)
