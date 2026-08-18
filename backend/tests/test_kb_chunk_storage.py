from __future__ import annotations

import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ai.knowledge.chunk_storage import persist_chunk_result
from ai.knowledge.models import KbChunk


class ChunkStorageTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        KbChunk.__table__.create(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def tearDown(self):
        self.engine.dispose()

    @staticmethod
    def _result():
        leaves = [
            {
                "doc_id": "doc-1",
                "chunk_index": index,
                "content": f"leaf-{index}",
                "token_count": 2,
                "depth": 1,
                "chunk_type": "paragraph",
                "section_path": "同一章节",
            }
            for index in range(4)
        ]
        parents = [
            {
                "doc_id": "doc-1",
                "chunk_index": 100000,
                "content": "leaf-0\n\nleaf-1",
                "token_count": 4,
                "depth": 0,
                "chunk_type": "parent",
                "section_path": "同一章节",
                "child_chunk_indexes": [0, 1],
            },
            {
                "doc_id": "doc-1",
                "chunk_index": 100001,
                "content": "leaf-2\n\nleaf-3",
                "token_count": 4,
                "depth": 0,
                "chunk_type": "parent",
                "section_path": "同一章节",
                "child_chunk_indexes": [2, 3],
            },
        ]
        return {"leaf": leaves, "parent": parents}

    def test_persists_exact_parent_for_each_leaf(self):
        db = self.Session()
        try:
            stats = persist_chunk_result(db, self._result())
            db.commit()

            leaves = db.query(KbChunk).filter_by(depth=1).order_by(
                KbChunk.chunk_index
            ).all()
            parents = db.query(KbChunk).filter_by(depth=0).order_by(
                KbChunk.chunk_index
            ).all()
            self.assertEqual(stats["leaf_count"], 4)
            self.assertEqual(stats["parent_count"], 2)
            self.assertEqual(
                [leaf.parent_id for leaf in leaves],
                [parents[0].id, parents[0].id, parents[1].id, parents[1].id],
            )
        finally:
            db.close()

    def test_rejects_one_leaf_assigned_to_multiple_parents(self):
        result = self._result()
        result["parent"][1]["child_chunk_indexes"] = [1, 2, 3]
        db = self.Session()
        try:
            with self.assertRaisesRegex(ValueError, "multiple parents"):
                persist_chunk_result(db, result)
            self.assertEqual(db.query(KbChunk).count(), 0)
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
