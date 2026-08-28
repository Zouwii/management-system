"""Knowledge-base pipeline: metadata -> Markdown -> optional rechunk/embed.

Called by:
  - Daemon thread in app.py on a schedule (default: 04:00 BJT)
  - HTTP endpoint POST /ai/knowledge/sync-and-embedding
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List

from ai.knowledge.chunk_storage import persist_chunk_result
from ai.knowledge.chunk_strategy import chunk_document_for_index
from ai.knowledge.embedder import delete_vectors, embed_chunks
from ai.knowledge.markdown_sync import (
    download_markdown_documents,
    persist_downloaded_markdown,
)
from ai.knowledge.models import KbDocument, KbNode, KbChunk
from ai.knowledge.routes import _sync_workspace
from ai.knowledge.service import DingTalkKnowledgeClient, get_known_workspaces
from base.db.engine import KbSessionLocal, SessionLocal

logger = logging.getLogger(__name__)

_AUTO_CHUNK_EMBED_ENV = "KB_AUTO_CHUNK_EMBED_ENABLED"

_LOG_FILE = (
    Path(__file__).resolve().parent.parent.parent
    / "runtime" / "logs" / "ai_sync_embed.log"
)


def _sync_log(entry: dict) -> None:
    """Append a JSON log entry to the sync-embed pipeline log file."""
    try:
        _LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with _LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _resolve_union_id() -> str:
    """Resolve a union_id for automated operations (non-request context)."""
    from base.db.orm import UserCharacter as DbUserCharacter

    db = SessionLocal()
    try:
        row = (
            db.query(DbUserCharacter)
            .filter(
                DbUserCharacter.union_id.isnot(None),
                DbUserCharacter.union_id != "",
            )
            .first()
        )
        if row and row.union_id:
            return row.union_id
    finally:
        db.close()
    return ""


def _auto_chunk_embed_enabled() -> bool:
    """Whether sync may automatically rebuild chunks and vectors.

    Disabled by default while the Markdown import path is being stabilized.
    Explicit manual rechunk/reembed endpoints are intentionally unaffected.
    """
    return str(os.getenv(_AUTO_CHUNK_EMBED_ENV) or "").strip().lower() in (
        "1", "true", "yes", "on",
    )


def _sync_all_workspaces(client: DingTalkKnowledgeClient,
                        check_modified: bool = False,
                        limit: int = 0,
                        ws_limit: int = 0) -> dict:
    """Sync all known workspaces and return documents queued for Markdown."""
    known = get_known_workspaces()

    ws_list = client.list_workspaces()
    if not ws_list.get("ok"):
        return {"error": ws_list.get("error", "failed to list workspaces")}

    workspaces_to_sync: List[Dict[str, str]] = []
    for w in ws_list["data"]:
        ws_id = w.get("workspaceId", "")
        if ws_id in known:
            workspaces_to_sync.append(
                {
                    "workspaceId": ws_id,
                    "rootNodeId": w.get("rootNodeId", ""),
                    "name": w.get("name", ws_id),
                }
            )

    workspaces_to_sync.sort(key=lambda x: known.get(x["workspaceId"], 999))
    if ws_limit:
        workspaces_to_sync = workspaces_to_sync[:ws_limit]

    total_synced = 0
    total_failed = 0
    documents: List[dict] = []
    results: List[dict] = []

    for ws in workspaces_to_sync:
        ws_id = ws["workspaceId"]
        root_id = ws["rootNodeId"]
        ws_name = ws["name"]
        if not root_id:
            logger.warning("auto_sync: workspace %s has no rootNodeId, skipped", ws_id)
            continue

        ws_started = time.time()
        r = _sync_workspace(
            client,
            ws_id,
            root_id,
            limit=limit,
            check_modified=check_modified,
        )
        ws_elapsed = round(time.time() - ws_started, 1)
        ws_documents = r.get("syncedDocIds", [])
        documents.extend(ws_documents)
        results.append(
            {
                "workspaceId": ws_id,
                "name": ws_name,
                "syncedNodes": r["syncedNodes"],
                "queuedDocs": len(ws_documents),
                "failedNodes": r["failedNodes"],
                "failedDocs": r["failedDocs"],
                "errors": r["errors"],
                "durationSec": ws_elapsed,
            }
        )
        total_synced += len(ws_documents)
        total_failed += r["failedNodes"] + r["failedDocs"]
        skipped_info = ""
        if "skippedWorkbooks" in r:
            skipped_info = (
                f" skippedWb={r['skippedWorkbooks']}"
                f" skippedCached={r.get('skippedCached',0)}"
                f" skippedUnchanged={r.get('skippedUnchanged',0)}"
                f" skippedLegacy={r.get('skippedLegacy',0)}"
            )
        print(
            f"[auto_sync] workspace={ws_name} queued={len(ws_documents)}"
            f" failed={r['failedNodes'] + r['failedDocs']}{skipped_info} elapsed={ws_elapsed:.1f}s"
        )
        # Log first few errors for debugging
        ws_errors = r.get("errors", [])
        if ws_errors:
            for err in ws_errors[:5]:
                print(f"[sync-error-detail] workspace={ws_name} {err}")

    return {
        "ok": True,
        "totalSynced": total_synced,
        "totalFailed": total_failed,
        "documents": documents,
        "workspaces": results,
    }


def _rechunk_documents(doc_ids: List[str]) -> dict:
    """Re-chunk specific documents (drop old chunks, create new ones).

    Only processes the given doc_ids. Skips FTS rebuild since MySQL
    FULLTEXT indexes auto-maintain on row changes.
    """
    if not doc_ids:
        _sync_log({
            "ts": int(time.time()), "phase": "rechunk", "event": "skip",
            "reason": "no changed documents", "doc_count": 0,
        })
        return {"ok": True, "chunkedDocs": 0, "totalChunks": 0, "skipped": True}

    db = KbSessionLocal()
    try:
        total_chunks = 0
        docs = db.query(KbDocument).filter(
            KbDocument.node_id.in_(doc_ids),
            KbDocument.content != "",
        ).all()

        _sync_log({
            "ts": int(time.time()), "phase": "rechunk", "event": "start",
            "doc_count": len(docs), "doc_ids_count": len(doc_ids),
        })

        removed_chunk_ids: List[int] = []
        for doc in docs:
            removed_chunk_ids.extend(
                row[0]
                for row in db.query(KbChunk.id).filter(
                    KbChunk.doc_id == doc.node_id
                ).all()
            )
            db.query(KbChunk).filter(KbChunk.doc_id == doc.node_id).delete()
            node = db.query(KbNode.breadcrumb).filter(
                KbNode.node_id == doc.node_id
            ).first()
            result = chunk_document_for_index(
                doc.node_id,
                doc.title,
                doc.content,
                doc.outline or "",
                "FILE",
                node[0] if node else "",
            )
            persisted = persist_chunk_result(db, result)
            total_chunks += persisted["total_count"]
        db.commit()
        logger.info("auto_sync: rechunked %d docs -> %d chunks", len(docs), total_chunks)

        _sync_log({
            "ts": int(time.time()), "phase": "rechunk", "event": "done",
            "doc_count": len(docs), "total_chunks": total_chunks,
        })

        return {
            "ok": True,
            "chunkedDocs": len(docs),
            "totalChunks": total_chunks,
            "removedChunkIds": removed_chunk_ids,
        }
    except Exception as e:
        db.rollback()
        logger.exception("auto_sync: rechunk failed")
        _sync_log({
            "ts": int(time.time()), "phase": "rechunk", "event": "error",
            "error": str(e),
        })
        return {"ok": False, "error": str(e)}
    finally:
        db.close()


def sync_all_and_embed(union_id: str = "", check_modified: bool = False,
                       limit: int = 0, ws_limit: int = 0) -> dict:
    """Sync metadata and Markdown, with optional automatic rechunk/embed.

    check_modified=False: KB增量（仅拉取未缓存的新文档）
    check_modified=True:  KB变更（对比 modified_at，重拉已变更文档）

    Automatic rechunk/embed is disabled by default. Set
    KB_AUTO_CHUNK_EMBED_ENABLED=true to restore phases 3 and 4.
    """

    if not union_id:
        union_id = _resolve_union_id()
    if not union_id:
        logger.error("auto_sync: cannot resolve union_id, abort")
        _sync_log({
            "ts": int(time.time()), "phase": "pipeline", "event": "abort",
            "error": "cannot resolve union_id",
        })
        return {"ok": False, "error": "cannot resolve union_id"}

    started = time.time()
    overall: Dict[str, Any] = {}

    _sync_log({
        "ts": int(time.time()), "phase": "pipeline", "event": "start",
        "union_id": union_id[:8] + "...",
    })

    def _log(msg: str) -> None:
        ts = time.strftime("%H:%M:%S")
        line = f"[sync-embed {ts}] {msg}"
        logger.info(line)
        print(line, flush=True)

    # Phase 1: sync directory metadata and collect documents requiring refresh.
    _log("phase 1/4 — syncing knowledge-base metadata...")
    _sync_log({
        "ts": int(time.time()), "phase": "pipeline", "event": "phase1_start",
        "phase": "sync",
    })
    client = DingTalkKnowledgeClient(union_id)
    phase1_start = time.time()
    sync_result = _sync_all_workspaces(
        client,
        check_modified=check_modified,
        limit=max(0, int(limit or 0)),
        ws_limit=max(0, int(ws_limit or 0)),
    )
    overall["sync"] = sync_result
    phase1_elapsed = round(time.time() - phase1_start, 1)
    if not sync_result.get("ok"):
        _log(f"sync FAILED after {phase1_elapsed}s: {sync_result.get('error', 'unknown')}")
        overall["ok"] = False
        overall["error"] = sync_result.get("error", "sync failed")
        overall["durationSec"] = round(time.time() - started, 1)
        _sync_log({
            "ts": int(time.time()), "phase": "pipeline", "event": "phase1_failed",
            "error": sync_result.get("error"), "elapsed": phase1_elapsed,
        })
        return overall

    documents = sync_result.get("documents", [])
    _log(
        f"phase 1 done ({phase1_elapsed}s) — "
        f"queued={len(documents)} failed={sync_result['totalFailed']}"
    )
    _sync_log({
        "ts": int(time.time()), "phase": "pipeline", "event": "phase1_done",
        "total_synced": sync_result["totalSynced"],
        "queued_count": len(documents),
        "failed": sync_result["totalFailed"],
        "elapsed": phase1_elapsed,
    })

    # Phase 2: fetch Markdown and only then replace document content.
    _log(f"phase 2/4 — downloading {len(documents)} Markdown documents...")
    _sync_log({
        "ts": int(time.time()), "phase": "pipeline", "event": "phase2_start",
        "phase": "markdown", "document_count": len(documents),
    })
    phase2_start = time.time()
    download_result = download_markdown_documents(documents)
    markdown_result = persist_downloaded_markdown(download_result)
    overall["markdown"] = markdown_result
    phase2_elapsed = round(time.time() - phase2_start, 1)
    _log(
        f"phase 2 done ({phase2_elapsed}s) — "
        f"changed={markdown_result['changed']} unchanged={markdown_result['unchanged']} "
        f"failed={markdown_result['failed']}"
    )
    _sync_log({
        "ts": int(time.time()), "phase": "pipeline", "event": "phase2_done",
        "changed": markdown_result["changed"],
        "unchanged": markdown_result["unchanged"],
        "failed": markdown_result["failed"],
        "elapsed": phase2_elapsed,
        "ok": markdown_result["ok"],
    })

    if documents and not download_result.get("downloaded"):
        overall["ok"] = False
        overall["error"] = download_result.get("error") or "all Markdown downloads failed"
        overall["durationSec"] = round(time.time() - started, 1)
        return overall

    changed_ids = markdown_result["changedIds"]

    # Markdown backfill is not stable yet. Keep downloaded content in
    # kb_documents, but do not mutate existing chunks or vectors unless the
    # automatic post-processing switch is explicitly enabled.
    if not _auto_chunk_embed_enabled():
        reason = f"disabled; set {_AUTO_CHUNK_EMBED_ENV}=true to enable"
        overall["autoChunkEmbedEnabled"] = False
        overall["rechunk"] = {
            "ok": True,
            "skipped": True,
            "reason": reason,
            "changedDocs": len(changed_ids),
        }
        overall["embed"] = {
            "ok": True,
            "skipped": True,
            "reason": reason,
        }
        overall["ok"] = bool(markdown_result["ok"])
        if not overall["ok"]:
            overall["error"] = "one or more Markdown downloads failed"
        overall["durationSec"] = round(time.time() - started, 1)
        _log(
            "phases 3/4 skipped — automatic rechunk and embedding are disabled; "
            f"Markdown changed={len(changed_ids)}"
        )
        _sync_log({
            "ts": int(time.time()),
            "phase": "pipeline",
            "event": "postprocess_skipped",
            "reason": reason,
            "changed_docs": len(changed_ids),
        })
        _sync_log({
            "ts": int(time.time()),
            "phase": "pipeline",
            "event": "done",
            "duration_sec": overall["durationSec"],
            "phase1_elapsed": phase1_elapsed,
            "phase2_elapsed": phase2_elapsed,
            "postprocess_skipped": True,
        })
        return overall

    overall["autoChunkEmbedEnabled"] = True

    # Phase 3: rechunk only documents whose Markdown body changed.
    _log(f"phase 3/4 — rechunking {len(changed_ids)} changed documents...")
    phase3_start = time.time()
    rechunk_result = _rechunk_documents(changed_ids)
    overall["rechunk"] = rechunk_result
    phase3_elapsed = round(time.time() - phase3_start, 1)
    if not rechunk_result.get("ok"):
        overall["ok"] = False
        overall["error"] = rechunk_result.get("error", "rechunk failed")
        overall["durationSec"] = round(time.time() - started, 1)
        return overall
    try:
        removed_vector_count = delete_vectors(rechunk_result.get("removedChunkIds", []))
    except Exception as exc:
        logger.exception("auto_sync: deleting stale vectors failed")
        overall["ok"] = False
        overall["error"] = f"deleting stale vectors failed: {exc}"
        overall["durationSec"] = round(time.time() - started, 1)
        return overall
    overall["rechunk"]["removedVectors"] = removed_vector_count
    _log(
        f"phase 3 done ({phase3_elapsed}s) — "
        f"docs={rechunk_result.get('chunkedDocs', 0)} chunks={rechunk_result.get('totalChunks', 0)}"
    )

    # Phase 4: embed leaf chunks (idempotent — skips already-embedded)
    _log("phase 4/4 — embedding leaf chunks...")
    _sync_log({
        "ts": int(time.time()), "phase": "pipeline", "event": "phase4_start",
        "phase": "embed",
    })
    phase4_start = time.time()
    try:
        embed_result = embed_chunks(limit=0, depth=1)
        overall["embed"] = {
            "ok": True,
            "chunkTotal": embed_result.get("chunk_total", 0),
            "embedded": embed_result.get("embedded", 0),
            "skipped": embed_result.get("skipped", 0),
            "errors": embed_result.get("errors", 0),
        }
        phase4_elapsed = round(time.time() - phase4_start, 1)
        _log(
            f"phase 4 done ({phase4_elapsed}s) — "
            f"total={embed_result.get('chunk_total', 0)} new={embed_result.get('embedded', 0)} "
            f"skipped={embed_result.get('skipped', 0)} errors={embed_result.get('errors', 0)}"
        )
        _sync_log({
            "ts": int(time.time()), "phase": "pipeline", "event": "phase4_done",
            "chunk_total": embed_result.get("chunk_total", 0),
            "embedded": embed_result.get("embedded", 0),
            "skipped": embed_result.get("skipped", 0),
            "errors": embed_result.get("errors", 0),
            "elapsed": phase4_elapsed,
        })
    except Exception as e:
        logger.exception("auto_sync: embed phase failed")
        overall["embed"] = {"ok": False, "error": str(e)}
        overall["ok"] = False
        overall["error"] = f"embedding failed: {e}"
        _sync_log({
            "ts": int(time.time()), "phase": "pipeline", "event": "phase4_error",
            "error": str(e),
        })

    if "ok" not in overall:
        embedding_ok = not bool(overall.get("embed", {}).get("errors"))
        overall["ok"] = bool(markdown_result["ok"] and embedding_ok)
        if not overall["ok"]:
            overall["error"] = (
                "one or more Markdown downloads failed"
                if not markdown_result["ok"]
                else "one or more embedding batches failed"
            )
    overall["durationSec"] = round(time.time() - started, 1)
    _log(
        f"pipeline done — total {overall['durationSec']}s "
        f"(sync={phase1_elapsed}s markdown={phase2_elapsed}s rechunk={phase3_elapsed}s)"
    )

    _sync_log({
        "ts": int(time.time()), "phase": "pipeline", "event": "done",
        "duration_sec": overall["durationSec"],
        "phase1_elapsed": phase1_elapsed,
        "phase2_elapsed": phase2_elapsed,
        "phase3_elapsed": phase3_elapsed,
    })

    return overall


# ---------------------------------------------------------------------------
# 便捷入口：四个主体函数
#   kb_incremental_sync  — KB小更新：仅拉取新增及 modifiedTime 变更文档
#   kb_full_sync         — KB大更新：对比 modified_at，重拉已变更文档
# ---------------------------------------------------------------------------

def kb_incremental_sync() -> dict:
    """KB小更新：只下载新增或 modifiedTime 变新的 Markdown。"""
    if not str(os.getenv("DINGTALK_KB_MCP_URL") or "").strip():
        return {
            "ok": False,
            "error": "missing DINGTALK_KB_MCP_URL; incremental sync aborted before metadata scan",
        }
    return sync_all_and_embed(check_modified=True)


def kb_full_sync() -> dict:
    """KB大更新：对比 modified_at，重拉新文档及已变更文档（check_modified=True）。"""
    return sync_all_and_embed(check_modified=True)
