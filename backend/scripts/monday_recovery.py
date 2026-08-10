"""One-off Monday recovery: TB first, then the unfinished KB workspace.

Run from ``backend/`` on the server. The normal Monday limit is applied
automatically by ``ApiCallMonitor``. This intentionally does not rebuild
chunks or embeddings.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))
load_dotenv(BACKEND_DIR / ".env")

from ai.knowledge.markdown_sync import (  # noqa: E402
    download_markdown_documents,
    persist_downloaded_markdown,
)
from ai.knowledge.models import KbNode  # noqa: E402
from ai.knowledge.routes import _sync_workspace  # noqa: E402
from ai.knowledge.service import DingTalkKnowledgeClient  # noqa: E402
from base.api_monitor import monitor  # noqa: E402
from base.config.service import get_config_projectids  # noqa: E402
from base.db.engine import KbSessionLocal, SessionLocal  # noqa: E402
from base.sync.task_sync import benti_team_incremental_update_service  # noqa: E402


DEFAULT_WORKSPACE_ID = "MJ0pDSwlOEkMqQ0E"  # 订单项目信息门户（周一扫描中断处）


def _resolve_union_id() -> str:
    from base.db.orm import UserCharacter

    db = SessionLocal()
    try:
        row = (
            db.query(UserCharacter)
            .filter(UserCharacter.union_id.isnot(None), UserCharacter.union_id != "")
            .first()
        )
        return str(row.union_id or "") if row else ""
    finally:
        db.close()


def _resolve_root_id(workspace_id: str) -> str:
    db = KbSessionLocal()
    try:
        row = (
            db.query(KbNode)
            .filter(
                KbNode.workspace_id == workspace_id,
                KbNode.parent_id == "",
                KbNode.node_type == "FOLDER",
            )
            .order_by(KbNode.depth.asc(), KbNode.id.asc())
            .first()
        )
        return str(row.node_id or "") if row else ""
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-id", default=DEFAULT_WORKSPACE_ID)
    args = parser.parse_args()

    monitor._ensure_state()
    projectids = get_config_projectids() or {}
    project_id = str(next(iter(projectids.values()), "") or "").strip()
    if not project_id:
        print(json.dumps({"ok": False, "phase": "tb", "error": "missing projectId"}, ensure_ascii=False))
        return 2

    tb = benti_team_incremental_update_service({"projectId": project_id})
    if not tb.get("success"):
        print(json.dumps({"ok": False, "phase": "tb", "tb": tb}, ensure_ascii=False))
        return 1

    union_id = _resolve_union_id()
    root_id = _resolve_root_id(args.workspace_id)
    if not union_id or not root_id:
        print(json.dumps({
            "ok": False,
            "phase": "kb",
            "error": "cannot resolve KB union_id or cached root node",
            "tb": tb,
        }, ensure_ascii=False))
        return 2

    client = DingTalkKnowledgeClient(union_id)
    sync = _sync_workspace(
        client,
        args.workspace_id,
        root_id,
        check_modified=True,
    )
    documents = sync.get("syncedDocIds", [])
    download = download_markdown_documents(documents)
    markdown = persist_downloaded_markdown(download)
    result = {
        "ok": bool(sync.get("failedNodes", 0) == 0 and markdown.get("ok", False)),
        "tb": tb,
        "workspace_id": args.workspace_id,
        "sync": {
            "synced_nodes": sync.get("syncedNodes", 0),
            "queued_documents": len(documents),
            "failed_nodes": sync.get("failedNodes", 0),
            "skipped_cached": sync.get("skippedCached", 0),
            "skipped_unchanged": sync.get("skippedUnchanged", 0),
            "skipped_legacy": sync.get("skippedLegacy", 0),
        },
        "markdown": {
            "changed": markdown.get("changed", 0),
            "unchanged": markdown.get("unchanged", 0),
            "failed": markdown.get("failed", 0),
        },
    }
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
