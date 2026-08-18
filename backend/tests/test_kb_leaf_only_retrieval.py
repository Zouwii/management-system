from __future__ import annotations

import inspect
import unittest
from unittest.mock import patch

from ai.knowledge.embedder import embed_chunks
from ai.knowledge import embedder, retriever
from ai.knowledge.retriever import _search_mysql, _search_sqlite


class _CapturingSession:
    def __init__(self, rows=None):
        self.statements = []
        self.rows = rows or []

    def execute(self, statement, params):
        self.statements.append((str(statement), params))
        rows = self.rows

        class Result:
            @staticmethod
            def fetchall():
                return rows

        return Result()

    def close(self):
        pass


class _Model:
    @staticmethod
    def encode(*_args, **_kwargs):
        return [[0.1, 0.2]]


class LeafOnlyRetrievalTests(unittest.TestCase):
    def test_embedding_defaults_to_leaf_depth(self):
        depth = inspect.signature(embed_chunks).parameters["depth"]
        self.assertEqual(depth.default, 1)

    def test_mysql_keyword_search_filters_to_leaf_depth(self):
        db = _CapturingSession()
        _search_mysql(db, "测试", 10, None)
        self.assertIn("c.depth = 1", db.statements[0][0])

    def test_mysql_workspace_search_filters_to_leaf_depth(self):
        db = _CapturingSession()
        _search_mysql(db, "测试", 10, "workspace-1")
        self.assertIn("c.depth = 1", db.statements[0][0])

    def test_sqlite_keyword_search_filters_to_leaf_depth(self):
        db = _CapturingSession()
        _search_sqlite(db, "测试", 10, None)
        self.assertIn("c.depth = 1", db.statements[0][0])

    def test_vector_metadata_lookup_filters_to_leaf_depth(self):
        pg = _CapturingSession(rows=[(11, 0.9)])
        kb = _CapturingSession(rows=[])
        with patch.object(embedder, "is_model_ready", return_value=True), patch.object(
            embedder, "_get_model", return_value=_Model()
        ), patch.object(
            retriever, "PgVectorSessionLocal", return_value=pg
        ), patch.object(
            retriever, "KbSessionLocal", return_value=kb
        ):
            self.assertEqual(retriever.search_vector("测试", top_k=5), [])

        self.assertIn("c.depth = 1", kb.statements[0][0])


if __name__ == "__main__":
    unittest.main()
