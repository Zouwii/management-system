"""Full knowledge-base update pipeline: sync -> rechunk -> embed.

Called by:
  - Daemon thread in app.py on a schedule (default: 04:00 BJT)
  - HTTP endpoint POST /ai/knowledge/full-update
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List

from ai.knowledge.chunker import chunk_document
from ai.knowledge.embedder import embed_chunks
from ai.knowledge.models import KbDocument, KbChunk
from ai.knowledge.routes import _sync_workspace
from ai.knowledge.service import DingTalkKnowledgeClient, get_known_workspaces
from db.engine import SessionLocal

logger = logging.getLogger(__name__)

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
    from db.orm import UserCharacter as DbUserCharacter

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


def _sync_all_workspaces(client: DingTalkKnowledgeClient,
                        full_sync: bool = False) -> dict:
    """Sync all known workspaces. Returns aggregated results with changedIds."""
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

    total_synced = 0
    total_changed = 0
    total_failed = 0
    all_changed_ids: List[str] = []
    results: List[dict] = []

    for ws in workspaces_to_sync:
        ws_id = ws["workspaceId"]
        root_id = ws["rootNodeId"]
        ws_name = ws["name"]
        if not root_id:
            logger.warning("auto_sync: workspace %s has no rootNodeId, skipped", ws_id)
            continue

        ws_started = time.time()
        r = _sync_workspace(client, ws_id, root_id, full_sync=full_sync)
        ws_elapsed = round(time.time() - ws_started, 1)
        ws_changed = r.get("syncedIds", [])
        all_changed_ids.extend(ws_changed)
        results.append(
            {
                "workspaceId": ws_id,
                "name": ws_name,
                "syncedCount": r["syncedCount"],
                "changedCount": r.get("changedCount", 0),
                "failedCount": r["failedCount"],
                "errors": r["errors"],
                "durationSec": ws_elapsed,
            }
        )
        total_synced += r["syncedCount"]
        total_changed += r.get("changedCount", 0)
        total_failed += r["failedCount"]
        logger.info(
            "auto_sync: workspace=%s synced=%d changed=%d failed=%d elapsed=%.1fs",
            ws_name, r["syncedCount"], r.get("changedCount", 0), r["failedCount"], ws_elapsed,
        )

    return {
        "ok": True,
        "totalSynced": total_synced,
        "totalChanged": total_changed,
        "totalFailed": total_failed,
        "changedIds": all_changed_ids,
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

    db = SessionLocal()
    try:
        total_chunks = 0
        docs = db.query(KbDocument).filter(
            KbDocument.doc_id.in_(doc_ids),
            KbDocument.content != "",
        ).all()

        _sync_log({
            "ts": int(time.time()), "phase": "rechunk", "event": "start",
            "doc_count": len(docs), "doc_ids_count": len(doc_ids),
        })

        for doc in docs:
            db.query(KbChunk).filter(KbChunk.doc_id == doc.doc_id).delete()
            chunks = chunk_document(doc.doc_id, doc.title, doc.content, doc.node_type)
            for c in chunks:
                db.add(
                    KbChunk(
                        doc_id=c["doc_id"],
                        chunk_index=c["chunk_index"],
                        content=c["content"],
                        token_count=c["token_count"],
                    )
                )
            total_chunks += len(chunks)
        db.commit()
        logger.info("auto_sync: rechunked %d docs -> %d chunks", len(docs), total_chunks)

        _sync_log({
            "ts": int(time.time()), "phase": "rechunk", "event": "done",
            "doc_count": len(docs), "total_chunks": total_chunks,
        })

        return {"ok": True, "chunkedDocs": len(docs), "totalChunks": total_chunks}
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


def sync_all_and_embed(union_id: str = "", full_sync: bool = False) -> dict:
    """Run the full pipeline: sync all KBs -> rechunk -> embed.

    full_sync=False (小同步): 增量拉取 + rechunk 变更 + embed 增量
    full_sync=True  (大同步): 对比修改时间重拉 + 全量 rechunk + embed
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

    # Phase 1: sync all workspaces
    _log("phase 1/3 — syncing all knowledge bases...")
    _sync_log({
        "ts": int(time.time()), "phase": "pipeline", "event": "phase1_start",
        "phase": "sync",
    })
    client = DingTalkKnowledgeClient(union_id)
    phase1_start = time.time()
    sync_result = _sync_all_workspaces(client, full_sync=full_sync)
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

    changed_ids = sync_result.get("changedIds", [])
    _log(
        f"phase 1 done ({phase1_elapsed}s) — "
        f"total={sync_result['totalSynced']} changed={len(changed_ids)} failed={sync_result['totalFailed']}"
    )
    _sync_log({
        "ts": int(time.time()), "phase": "pipeline", "event": "phase1_done",
        "total_synced": sync_result["totalSynced"],
        "changed_count": len(changed_ids),
        "failed": sync_result["totalFailed"],
        "elapsed": phase1_elapsed,
    })

    # Phase 2: rechunk only the documents that actually changed
    _log(f"phase 2/3 — rechunking {len(changed_ids)} changed documents...")
    _sync_log({
        "ts": int(time.time()), "phase": "pipeline", "event": "phase2_start",
        "phase": "rechunk", "changed_ids_count": len(changed_ids),
    })
    phase2_start = time.time()
    rechunk_result = _rechunk_documents(changed_ids)
    overall["rechunk"] = rechunk_result
    phase2_elapsed = round(time.time() - phase2_start, 1)
    _log(
        f"phase 2 done ({phase2_elapsed}s) — "
        f"docs={rechunk_result.get('chunkedDocs', 0)} chunks={rechunk_result.get('totalChunks', 0)}"
    )
    _sync_log({
        "ts": int(time.time()), "phase": "pipeline", "event": "phase2_done",
        "docs": rechunk_result.get("chunkedDocs", 0),
        "chunks": rechunk_result.get("totalChunks", 0),
        "elapsed": phase2_elapsed,
        "ok": rechunk_result.get("ok", True),
    })

    # Phase 3: embed all chunks (idempotent — skips already-embedded)
    _log("phase 3/3 — embedding all chunks...")
    _sync_log({
        "ts": int(time.time()), "phase": "pipeline", "event": "phase3_start",
        "phase": "embed",
    })
    phase3_start = time.time()
    try:
        embed_result = embed_chunks(limit=0)
        overall["embed"] = {
            "ok": True,
            "chunkTotal": embed_result.get("chunk_total", 0),
            "embedded": embed_result.get("embedded", 0),
            "skipped": embed_result.get("skipped", 0),
            "errors": embed_result.get("errors", 0),
        }
        phase3_elapsed = round(time.time() - phase3_start, 1)
        _log(
            f"phase 3 done ({phase3_elapsed}s) — "
            f"total={embed_result.get('chunk_total', 0)} new={embed_result.get('embedded', 0)} "
            f"skipped={embed_result.get('skipped', 0)} errors={embed_result.get('errors', 0)}"
        )
        _sync_log({
            "ts": int(time.time()), "phase": "pipeline", "event": "phase3_done",
            "chunk_total": embed_result.get("chunk_total", 0),
            "embedded": embed_result.get("embedded", 0),
            "skipped": embed_result.get("skipped", 0),
            "errors": embed_result.get("errors", 0),
            "elapsed": phase3_elapsed,
        })
    except Exception as e:
        logger.exception("auto_sync: embed phase failed")
        overall["embed"] = {"ok": False, "error": str(e)}
        _sync_log({
            "ts": int(time.time()), "phase": "pipeline", "event": "phase3_error",
            "error": str(e),
        })

    overall["ok"] = True
    overall["durationSec"] = round(time.time() - started, 1)
    _log(f"pipeline done — total {overall['durationSec']}s (sync={phase1_elapsed}s rechunk={phase2_elapsed}s)")

    _sync_log({
        "ts": int(time.time()), "phase": "pipeline", "event": "done",
        "duration_sec": overall["durationSec"],
        "phase1_elapsed": phase1_elapsed,
        "phase2_elapsed": phase2_elapsed,
    })

    return overall
