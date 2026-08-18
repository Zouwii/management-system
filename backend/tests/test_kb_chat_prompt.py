from __future__ import annotations

import json
import unittest

from ai.knowledge.chat import _build_system_content, chat_stream


class KnowledgeChatPromptTests(unittest.TestCase):
    def test_sse_prompt_is_answer_only_and_contains_context(self):
        prompt = _build_system_content(
            kb_context="导航到点需要先选择目标点。",
            tb_context="TB 任务数据（张三）：\n- [进行中] 联调",
        )

        self.assertIn("后端已经完成资料检索", prompt)
        self.assertIn("导航到点需要先选择目标点", prompt)
        self.assertIn("TB 任务数据（张三）", prompt)
        self.assertIn("不能调用或模拟任何工具", prompt)

        lowered = prompt.lower()
        for forbidden in ("curl", "tool_call", "<invoke", "ai_flask_base_url"):
            self.assertNotIn(forbidden, lowered)

    def test_sse_starts_with_retrieval_status_not_skill_loading(self):
        stream = chat_stream("测试问题")
        first_event = next(stream)
        payload = json.loads(first_event.split("data: ", 1)[1])

        self.assertEqual(payload["type"], "status")
        self.assertEqual(payload["content"], "检索本地向量知识库")


if __name__ == "__main__":
    unittest.main()
