from __future__ import annotations

import json
import os
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ai.knowledge import auto_sync, markdown_sync, routes
from ai.knowledge.models import KbBase, KbChunk, KbDocument, KbNode


class _FakeResponse:
    def __init__(self, payload, status_error=None):
        self._payload = payload
        self._status_error = status_error

    def raise_for_status(self):
        if self._status_error:
            raise self._status_error

    def json(self):
        return self._payload


class MarkdownDownloadTests(unittest.TestCase):
    def test_extract_markdown_from_mcp_response(self):
        document = {"success": True, "title": "demo", "markdown": "# Demo\nbody"}
        response = _FakeResponse({
            "result": {"content": [{"text": json.dumps(document)}]},
        })

        markdown, source = markdown_sync._extract_markdown(response)

        self.assertEqual(markdown, "# Demo\nbody")
        self.assertEqual(source["title"], "demo")

    def test_missing_mcp_url_fails_without_network_request(self):
        with patch.dict("os.environ", {}, clear=True), patch.object(
            markdown_sync.requests, "post"
        ) as post:
            result = markdown_sync.download_markdown_documents([
                {"node_id": "node-1", "title": "Demo"},
            ])

        self.assertFalse(result["ok"])
        self.assertEqual(result["failed"][0]["node_id"], "node-1")
        post.assert_not_called()

    def test_download_uses_configured_mcp_url(self):
        document = {"success": True, "markdown": "# Downloaded"}
        response = _FakeResponse({
            "result": {"content": [{"text": json.dumps(document)}]},
        })
        with patch.object(markdown_sync.requests, "post", return_value=response) as post:
            result = markdown_sync.download_markdown_documents(
                [{"node_id": "node-1"}],
                mcp_url="https://example.invalid/mcp",
                workers=1,
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["downloaded"][0]["markdown"], "# Downloaded")
        self.assertEqual(post.call_args.args[0], "https://example.invalid/mcp")

    def test_persist_keeps_old_content_when_download_failed(self):
        successful_row = SimpleNamespace(
            content="old-success",
            outline="",
            fetch_status="success",
            fail_reason="",
            synced_at=None,
            updated_at=None,
        )
        failed_row = SimpleNamespace(
            content="old-must-survive",
            outline="old-raw",
            fetch_status="success",
            fail_reason="",
            synced_at=None,
            updated_at=None,
        )

        class FakeQuery:
            def __init__(self, rows):
                self.rows = rows

            def filter(self, *_args):
                return self

            def first(self):
                return self.rows.pop(0)

        class FakeSession:
            def __init__(self):
                self.rows = [successful_row, failed_row]
                self.committed = False

            def query(self, *_args):
                return FakeQuery(self.rows)

            def commit(self):
                self.committed = True

            def rollback(self):
                pass

            def close(self):
                pass

        session = FakeSession()
        with patch.object(markdown_sync, "KbSessionLocal", return_value=session):
            result = markdown_sync.persist_downloaded_markdown({
                "downloaded": [{
                    "node_id": "node-ok",
                    "markdown": "# New",
                    "source_payload": {"success": True},
                }],
                "failed": [{"node_id": "node-failed", "error": "timeout"}],
            })

        self.assertTrue(session.committed)
        self.assertEqual(successful_row.content, "# New")
        sync_meta = json.loads(successful_row.outline)["_management_system"]
        self.assertEqual(sync_meta["source"], "mcp_markdown")
        self.assertEqual(failed_row.content, "old-must-survive")
        self.assertEqual(failed_row.fetch_status, "success")
        self.assertEqual(failed_row.fail_reason, "timeout")
        self.assertEqual(result["changedIds"], ["node-ok"])

    def test_persist_marks_failed_only_when_no_cached_content(self):
        row = SimpleNamespace(
            content="",
            outline="",
            fetch_status="pending",
            fail_reason="",
            synced_at=None,
            updated_at=None,
        )

        class FakeQuery:
            def filter(self, *_args):
                return self

            def first(self):
                return row

        class FakeSession:
            def query(self, *_args):
                return FakeQuery()

            def commit(self):
                pass

            def rollback(self):
                pass

            def close(self):
                pass

        with patch.object(markdown_sync, "KbSessionLocal", return_value=FakeSession()):
            markdown_sync.persist_downloaded_markdown({
                "downloaded": [],
                "failed": [{"node_id": "new-node", "error": "timeout"}],
            })

        self.assertEqual(row.fetch_status, "failed")


class IncrementalSyncTests(unittest.TestCase):
    def test_incremental_sync_aborts_before_scan_without_mcp_url(self):
        with patch.dict("os.environ", {}, clear=True), patch.object(
            auto_sync, "sync_all_and_embed"
        ) as pipeline:
            result = auto_sync.kb_incremental_sync()

        self.assertFalse(result["ok"])
        self.assertIn("DINGTALK_KB_MCP_URL", result["error"])
        pipeline.assert_not_called()

    def test_incremental_sync_downloads_new_and_modified_documents(self):
        with patch.dict(
            "os.environ", {"DINGTALK_KB_MCP_URL": "https://example.invalid/mcp"}, clear=True
        ), patch.object(
            auto_sync, "sync_all_and_embed", return_value={"ok": True}
        ) as pipeline:
            result = auto_sync.kb_incremental_sync()

        self.assertTrue(result["ok"])
        pipeline.assert_called_once_with(check_modified=True)


class PipelineTests(unittest.TestCase):
    def test_only_markdown_origin_cache_is_considered_ready(self):
        legacy = SimpleNamespace(outline=json.dumps({"data": {"blocks": []}}))
        markdown = SimpleNamespace(outline=json.dumps({"success": True, "markdown": "# Doc"}))
        local = SimpleNamespace(outline=json.dumps({"source": "local_markdown"}))

        self.assertFalse(routes._has_markdown_source(legacy))
        self.assertTrue(routes._has_markdown_source(markdown))
        self.assertTrue(routes._has_markdown_source(local))

    def test_weekly_sync_skips_legacy_and_queues_only_managed_delta(self):
        engine = create_engine("sqlite:///:memory:")
        KbBase.metadata.create_all(engine)
        session_factory = sessionmaker(bind=engine)
        old_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
        new_time = "2026-02-01T00:00:00Z"

        db = session_factory()
        for node_id in ("legacy", "unchanged", "changed", "retry"):
            db.add(KbNode(
                node_id=node_id,
                workspace_id="ws-1",
                parent_id="root-1",
                name=node_id,
                node_type="FILE",
                category="ALIDOC",
                has_children=False,
                depth=1,
                breadcrumb=node_id,
                remote_modified_at=old_time,
                sync_status="synced",
                synced_at=old_time,
                created_at=old_time,
                updated_at=old_time,
            ))
        db.add_all([
            KbDocument(
                node_id="legacy", workspace_id="ws-1", title="legacy",
                content="legacy body", outline=json.dumps({"ok": True, "data": {}}),
                fetch_status="failed", synced_at=old_time,
                created_at=old_time, updated_at=old_time,
            ),
            KbDocument(
                node_id="unchanged", workspace_id="ws-1", title="unchanged",
                content="# unchanged",
                outline=json.dumps({
                    "markdown": "# unchanged",
                    "_management_system": {
                        "source": "mcp_markdown",
                        "contentRemoteModifiedTime": old_time.isoformat(),
                    },
                }),
                fetch_status="success", synced_at=old_time,
                created_at=old_time, updated_at=old_time,
            ),
            KbDocument(
                node_id="changed", workspace_id="ws-1", title="changed",
                content="# old",
                outline=json.dumps({
                    "markdown": "# old",
                    "_management_system": {
                        "source": "mcp_markdown",
                        "contentRemoteModifiedTime": old_time.isoformat(),
                    },
                }),
                fetch_status="success", synced_at=old_time,
                created_at=old_time, updated_at=old_time,
            ),
            KbDocument(
                node_id="retry", workspace_id="ws-1", title="retry",
                content="",
                outline=json.dumps({
                    "_management_system": {"source": "mcp_pending"},
                }),
                fetch_status="failed", synced_at=old_time,
                created_at=old_time, updated_at=old_time,
            ),
        ])
        db.commit()
        db.close()

        nodes = []
        for node_id in ("legacy", "unchanged", "changed", "retry", "new"):
            modified = old_time.isoformat()
            if node_id == "changed":
                modified = new_time
            nodes.append({
                "nodeId": node_id,
                "type": "FILE",
                "name": node_id,
                "category": "ALIDOC",
                "hasChildren": False,
                "modifiedTime": modified,
            })
        client = SimpleNamespace(list_nodes=lambda _workspace, _parent: {
            "ok": True,
            "data": nodes,
        })

        with patch.object(routes, "KbSessionLocal", session_factory):
            result = routes._sync_workspace(
                client, "ws-1", "root-1", check_modified=True
            )

        queued = {item["node_id"] for item in result["syncedDocIds"]}
        self.assertEqual(queued, {"changed", "retry", "new"})
        self.assertEqual(result["skippedLegacy"], 1)
        self.assertEqual(result["skippedUnchanged"], 1)

        db = session_factory()
        try:
            legacy = db.query(KbDocument).filter_by(node_id="legacy").one()
            new = db.query(KbDocument).filter_by(node_id="new").one()
            self.assertEqual(legacy.fetch_status, "success")
            self.assertEqual(
                json.loads(new.outline)["_management_system"]["source"],
                "mcp_pending",
            )
        finally:
            db.close()
            engine.dispose()

    def test_sync_result_contract_uses_new_schema_fields(self):
        client = SimpleNamespace(list_workspaces=lambda: {
            "ok": True,
            "data": [{
                "workspaceId": "ws-1",
                "rootNodeId": "root-1",
                "name": "Workspace",
            }],
        })
        workspace_result = {
            "syncedNodes": 3,
            "syncedDocs": 1,
            "syncedDocIds": [{"node_id": "node-1", "workspace_id": "ws-1"}],
            "changedDocIds": [],
            "failedNodes": 0,
            "failedDocs": 0,
            "errors": [],
        }

        with patch.object(auto_sync, "get_known_workspaces", return_value={"ws-1": 1}), patch.object(
            auto_sync, "_sync_workspace", return_value=workspace_result
        ):
            result = auto_sync._sync_all_workspaces(client)

        self.assertTrue(result["ok"])
        self.assertEqual(result["totalSynced"], 1)
        self.assertEqual(result["documents"][0]["node_id"], "node-1")

    def test_markdown_persist_and_rechunk_with_sqlite(self):
        engine = create_engine("sqlite:///:memory:")
        KbBase.metadata.create_all(engine)
        session_factory = sessionmaker(bind=engine)
        now = datetime.now(timezone.utc)
        db = session_factory()
        db.add(KbDocument(
            node_id="node-1",
            workspace_id="ws-1",
            title="Demo",
            content="legacy body",
            outline="",
            fetch_status="pending",
            synced_at=now,
            created_at=now,
            updated_at=now,
        ))
        db.commit()
        db.close()

        with patch.object(markdown_sync, "KbSessionLocal", session_factory):
            persisted = markdown_sync.persist_downloaded_markdown({
                "downloaded": [{
                    "node_id": "node-1",
                    "markdown": "# Demo\n\nnew Markdown body",
                    "source_payload": {"success": True, "markdown": "# Demo"},
                }],
                "failed": [],
            })
        with patch.object(auto_sync, "KbSessionLocal", session_factory), patch.object(
            auto_sync, "_sync_log"
        ):
            rechunked = auto_sync._rechunk_documents(persisted["changedIds"])

        db = session_factory()
        try:
            document = db.query(KbDocument).filter_by(node_id="node-1").one()
            chunks = db.query(KbChunk).filter_by(doc_id="node-1").all()
            self.assertEqual(document.content, "# Demo\n\nnew Markdown body")
            self.assertEqual(document.fetch_status, "success")
            self.assertTrue(chunks)
            self.assertTrue(rechunked["ok"])
        finally:
            db.close()
            engine.dispose()

    def test_full_pipeline_skips_rechunk_and_embed_by_default(self):
        documents = [{"node_id": "node-1", "title": "Demo"}]
        calls = []

        with patch.dict(os.environ, {}, clear=True), patch.object(
            auto_sync, "DingTalkKnowledgeClient"
        ), patch.object(
            auto_sync,
            "_sync_all_workspaces",
            return_value={
                "ok": True,
                "totalSynced": 1,
                "totalFailed": 0,
                "documents": documents,
                "workspaces": [],
            },
        ), patch.object(
            auto_sync,
            "download_markdown_documents",
            side_effect=lambda docs: calls.append("download") or {
                "ok": True,
                "downloaded": [{**documents[0], "markdown": "# Demo"}],
                "failed": [],
            },
        ), patch.object(
            auto_sync,
            "persist_downloaded_markdown",
            side_effect=lambda result: calls.append("persist") or {
                "ok": True,
                "changedIds": ["node-1"],
                "changed": 1,
                "unchanged": 0,
                "failed": 0,
            },
        ), patch.object(auto_sync, "_rechunk_documents") as rechunk, patch.object(
            auto_sync, "delete_vectors"
        ) as delete_vectors_mock, patch.object(auto_sync, "embed_chunks") as embed:
            result = auto_sync.sync_all_and_embed(union_id="union-1")

        self.assertTrue(result["ok"])
        self.assertFalse(result["autoChunkEmbedEnabled"])
        self.assertTrue(result["rechunk"]["skipped"])
        self.assertTrue(result["embed"]["skipped"])
        self.assertEqual(calls, ["download", "persist"])
        rechunk.assert_not_called()
        delete_vectors_mock.assert_not_called()
        embed.assert_not_called()

    def test_full_pipeline_can_enable_rechunk_and_embed(self):
        documents = [{"node_id": "node-1", "title": "Demo"}]
        calls = []

        with patch.dict(
            os.environ, {"KB_AUTO_CHUNK_EMBED_ENABLED": "true"}, clear=True
        ), patch.object(auto_sync, "DingTalkKnowledgeClient"), patch.object(
            auto_sync,
            "_sync_all_workspaces",
            return_value={
                "ok": True,
                "totalSynced": 1,
                "totalFailed": 0,
                "documents": documents,
                "workspaces": [],
            },
        ), patch.object(
            auto_sync,
            "download_markdown_documents",
            side_effect=lambda docs: calls.append("download") or {
                "ok": True,
                "downloaded": [{**documents[0], "markdown": "# Demo"}],
                "failed": [],
            },
        ), patch.object(
            auto_sync,
            "persist_downloaded_markdown",
            side_effect=lambda result: calls.append("persist") or {
                "ok": True,
                "changedIds": ["node-1"],
                "changed": 1,
                "unchanged": 0,
                "failed": 0,
            },
        ), patch.object(
            auto_sync,
            "_rechunk_documents",
            side_effect=lambda ids: calls.append("rechunk") or {
                "ok": True,
                "chunkedDocs": 1,
                "totalChunks": 2,
                "removedChunkIds": [10],
            },
        ), patch.object(
            auto_sync, "delete_vectors", side_effect=lambda ids: calls.append("delete_vectors") or 1
        ), patch.object(
            auto_sync,
            "embed_chunks",
            side_effect=lambda **kwargs: calls.append("embed") or {
                "chunk_total": 2,
                "embedded": 2,
                "skipped": 0,
                "errors": 0,
            },
        ):
            result = auto_sync.sync_all_and_embed(union_id="union-1")

        self.assertTrue(result["ok"])
        self.assertTrue(result["autoChunkEmbedEnabled"])
        self.assertEqual(
            calls,
            ["download", "persist", "rechunk", "delete_vectors", "embed"],
        )

    def test_all_downloads_failed_stops_before_rechunk(self):
        documents = [{"node_id": "node-1"}]
        with patch.object(auto_sync, "DingTalkKnowledgeClient"), patch.object(
            auto_sync,
            "_sync_all_workspaces",
            return_value={
                "ok": True,
                "totalSynced": 1,
                "totalFailed": 0,
                "documents": documents,
                "workspaces": [],
            },
        ), patch.object(
            auto_sync,
            "download_markdown_documents",
            return_value={
                "ok": False,
                "downloaded": [],
                "failed": [{"node_id": "node-1", "error": "network"}],
            },
        ), patch.object(
            auto_sync,
            "persist_downloaded_markdown",
            return_value={
                "ok": False,
                "changedIds": [],
                "changed": 0,
                "unchanged": 0,
                "failed": 1,
            },
        ), patch.object(auto_sync, "_rechunk_documents") as rechunk:
            result = auto_sync.sync_all_and_embed(union_id="union-1")

        self.assertFalse(result["ok"])
        rechunk.assert_not_called()


if __name__ == "__main__":
    unittest.main()
