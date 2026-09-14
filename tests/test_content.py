"""内容生成 Agent 测试（对应 FR-05：三阶段、失败跳过、Checkpointer 恢复）。"""
import sys
import tempfile
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


class TestResume(unittest.TestCase):
    def test_resume_persists_progress(self):
        """resume 后新完成阶段回写检查点：再次 resume 不重跑已完成阶段。"""
        with tempfile.TemporaryDirectory() as tmp:
            agent = ContentAgent(
                LLMClient(LLMConfig()), retries=1, checkpointer=Checkpointer(path=tmp)
            )
            state = {
                "session_id": "s",
                "product": {"product_id": "P001", "name": "智能门锁 S1"},
                "task_id": "t-resume",
                "stages": {
                    "topic": {
                        "session_id": "s",
                        "stage": "topic",
                        "content": "已有选题",
                        "status": "done",
                        "task_id": "t-resume",
                        "created_at": "2026-01-01T00:00:00+00:00",
                    }
                },
            }
            agent.checkpointer.save("t-resume", state)

            results = agent.resume("t-resume", {"product_id": "P001"})
            self.assertEqual(
                {r.stage for r in results}, {ContentStage.COPY, ContentStage.SCRIPT}
            )

            saved = agent.checkpointer.load("t-resume")
            self.assertEqual(set(saved["stages"]), {"topic", "copy", "script"})
            self.assertEqual(saved["stages"]["topic"]["status"], "done")
            self.assertEqual(saved["stages"]["copy"]["status"], "done")

            # 全部阶段完成后再次 resume：无剩余阶段可跑
            self.assertEqual(agent.resume("t-resume", {"product_id": "P001"}), [])


if __name__ == "__main__":
    unittest.main()