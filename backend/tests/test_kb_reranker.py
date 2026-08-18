from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import Mock, patch

from ai.knowledge import reranker, retriever


class RerankerTests(unittest.TestCase):
    def setUp(self):
        reranker._reranker = None
        reranker._reranker_model = ""
        reranker._reranker_ready = False

    def tearDown(self):
        reranker._reranker = None
        reranker._reranker_model = ""
        reranker._reranker_ready = False

    def test_forces_cpu_with_flagembedding_devices_argument(self):
        instance = object()
        constructor = Mock(return_value=instance)
        fake_module = types.SimpleNamespace(FlagReranker=constructor)

        with patch.dict(sys.modules, {"FlagEmbedding": fake_module}):
            loaded = reranker.get_reranker("base")
            loaded_again = reranker.get_reranker("base")

        self.assertIs(loaded, instance)
        self.assertIs(loaded_again, instance)
        constructor.assert_called_once_with(
            str(reranker._get_model_dir("base")),
            use_fp16=False,
            devices="cpu",
        )
        self.assertTrue(reranker.is_reranker_ready())

    def test_search_falls_back_when_reranker_raises(self):
        candidates = [
            {"chunk_id": 1, "content": "候选一", "score": 0.2},
            {"chunk_id": 2, "content": "候选二", "score": 0.1},
        ]
        with patch.object(
            retriever, "search_hybrid", return_value=candidates
        ), patch.object(
            reranker, "rerank", side_effect=RuntimeError("reranker failed")
        ):
            results = retriever.search_with_rerank("测试", top_k=2)

        self.assertEqual(results, candidates)


if __name__ == "__main__":
    unittest.main()
