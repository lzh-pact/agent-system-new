"""内容生成 Agent 测试（对应 FR-05：三阶段、失败跳过、Checkpointer 恢复）。"""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app_core.config import LLMConfig  # noqa: E402
from app_core.llm import LLMClient  # noqa: E402
from app_core.models import ContentStage, ContentStatus  # noqa: E402
from agents.content import stages  # noqa: E402
from agents.content.graph import ContentAgent  # noqa: E402
from agents.content.persist import Checkpointer  # noqa: E402


class TestContentAgent(unittest.TestCase):
    def setUp(self):
        self.agent = ContentAgent(LLMClient(LLMConfig()), retries=1)

    def test_generates_three_stages(self):
        results = self.agent.generate("s", {"name": "智能门锁 S1"}, stage="all")
        self.assertEqual(
            [r.stage for r in results],
            [ContentStage.TOPIC, ContentStage.COPY, ContentStage.SCRIPT],
        )
        self.assertTrue(all(r.status == ContentStatus.DONE for r in results))
        self.assertTrue(all(r.content for r in results))

    def test_single_stage(self):
        results = self.agent.generate("s", {"name": "X"}, stage="copy")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].stage, ContentStage.COPY)

    def test_stage_failure_skips_node(self):
        def boom(llm, product_info):
            raise RuntimeError("gen fail")

        with patch.dict(stages.STAGE_GENERATORS, {ContentStage.TOPIC: boom}):
            results = self.agent.generate("s", {"name": "X"}, stage="topic")
        self.assertEqual(results[0].status, ContentStatus.FAILED)
        self.assertEqual(results[0].content, "")


class TestCheckpointer(unittest.TestCase):
    def test_roundtrip_and_delete(self):
        cp = Checkpointer(path="./data/checkpoints")
        cp.save("t1", {"a": 1})
        self.assertEqual(cp.load("t1"), {"a": 1})
        cp.delete("t1")
        self.assertIsNone(cp.load("t1"))


if __name__ == "__main__":
    unittest.main()