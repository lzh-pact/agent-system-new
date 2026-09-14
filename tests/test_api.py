"""API 网关测试（模块 F）：REST 接口在离线 Mock 模式下端到端可跑通。

覆盖会话、知识入库/检索、问答、商品目录、内容生成后台任务、数据管道
（含文件上传），与 run_tests.py 强制离线策略一致（不触网、零花费）。
"""
import json
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from api.main import app  # noqa: E402

client = TestClient(app)


def _wait_task(task_id: str, timeout: float = 30.0) -> dict:
    """轮询内容生成任务直至完成（Mock 模式下毫秒级返回）。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        task = client.get(f"/api/content/tasks/{task_id}").json()
        if task["status"] != "running":
            return task
        time.sleep(0.05)
    raise AssertionError(f"任务 {task_id} 超时未完成")


class TestHealthAndStats(unittest.TestCase):
    def test_health_offline_mock(self):
        resp = client.get("/api/health")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["llm_mode"], "mock")  # run_tests 强制清空 Key
        self.assertIn("retrieval", body)

    def test_stats_shape(self):
        body = client.get("/api/stats").json()
        for key in (
            "total_docs",
            "total_chunks",
            "total_sessions",
            "total_messages",
            "total_tasks",
        ):
            self.assertIn(key, body)


class TestSessions(unittest.TestCase):
    def test_create_list_history(self):
        created = client.post("/api/sessions", json={"user_id": "tester"}).json()
        self.assertTrue(created["session_id"])
        self.assertEqual(created["status"], "active")

        listed = client.get("/api/sessions").json()
        self.assertTrue(any(s["session_id"] == created["session_id"] for s in listed))

        history = client.get(f"/api/sessions/{created['session_id']}/history").json()
        self.assertEqual(history, [])

    def test_history_serializes_message_fields(self):
        created = client.post("/api/sessions").json()
        sid = created["session_id"]
        client.post("/api/ask", json={"session_id": sid, "query": "售后政策是什么？"})
        history = client.get(f"/api/sessions/{sid}/history").json()
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["role"], "user")
        self.assertEqual(history[1]["role"], "assistant")
        self.assertIn("created_at", history[0])  # datetime 已转 isoformat


class TestKnowledge(unittest.TestCase):
    def test_ingest_and_search(self):
        resp = client.post(
            "/api/knowledge/ingest",
            json={
                "title": "API 测试文档",
                "content": "API 测试：智能门锁 S1 支持指纹开锁，保修一年。",
                "source": "测试",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(resp.json()["chunks"], 1)

        hits = client.post(
            "/api/knowledge/search", json={"query": "门锁 指纹"}
        ).json()
        self.assertTrue(hits)
        self.assertIn("final_score", hits[0])
        self.assertIn("rank", hits[0])

    def test_sample_load(self):
        body = client.post("/api/knowledge/sample").json()
        self.assertEqual(len(body["entries"]), 4)
        self.assertGreaterEqual(body["total_chunks"], 4)

    def test_ingest_validation(self):
        resp = client.post("/api/knowledge/ingest", json={"title": "", "content": "x"})
        self.assertEqual(resp.status_code, 422)


class TestAsk(unittest.TestCase):
    def test_ask_returns_agent_answer(self):
        sid = client.post("/api/sessions").json()["session_id"]
        resp = client.post(
            "/api/ask", json={"session_id": sid, "query": "智能门锁 S1 的价格？"}
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("answer", body)
        self.assertIn("trace", body)
        self.assertIn("degraded", body)
        self.assertFalse(body["degraded"])  # Mock 模式不降级
        self.assertTrue(body["trace"])  # ReAct 轨迹非空

    def test_products_endpoint(self):
        products = client.get("/api/products").json()
        self.assertEqual(len(products), 3)
        p001 = next(p for p in products if p["product_id"] == "P001")
        self.assertEqual(p001["name"], "智能门锁 S1")
        self.assertTrue(p001["available"])


class TestContentTasks(unittest.TestCase):
    def test_generate_all_stages_with_progress(self):
        sid = client.post("/api/sessions").json()["session_id"]
        task = client.post(
            "/api/content/generate",
            json={"session_id": sid, "product_id": "P001", "name": "智能门锁 S1"},
        ).json()
        self.assertEqual(task["status"], "running")
        self.assertEqual(len(task["stages"]), 3)

        done = _wait_task(task["task_id"])
        self.assertEqual(done["status"], "done")
        self.assertEqual(done["error"], None)
        stages = {s["stage"]: s for s in done["stages"]}
        self.assertEqual(stages["topic"]["status"], "done")
        self.assertEqual(stages["copy"]["status"], "done")
        self.assertEqual(stages["script"]["status"], "done")
        for s in stages.values():
            self.assertTrue(s["content"])

    def test_task_list_and_unknown_task(self):
        listed = client.get("/api/content/tasks").json()
        self.assertIsInstance(listed, list)
        resp = client.get("/api/content/tasks/not-exist")
        self.assertEqual(resp.status_code, 404)

    def test_resume_unknown_task_404(self):
        resp = client.post("/api/content/resume", json={"task_id": "not-exist"})
        self.assertEqual(resp.status_code, 404)


class TestPipeline(unittest.TestCase):
    def test_sample_pipeline(self):
        body = client.post("/api/pipeline/sample").json()
        report = body["report"]
        stats = report["stage_stats"]
        # 6 条输入：1 条空值被清洗、1 条重复被去重 → 输出 4 条
        self.assertEqual(stats["input"], 6)
        self.assertEqual(stats["clean_dropped"], 1)
        self.assertEqual(stats["dedupe_removed"], 1)
        self.assertEqual(stats["output"], 4)
        self.assertEqual(report["total_records"], 4)
        self.assertEqual(body["masked_total"], 4)
        self.assertGreaterEqual(report["mask_hits"].get("phone", 0), 1)
        self.assertTrue(report["samples"])

    def test_upload_json_file(self):
        payload = json.dumps(
            [{"content": "联系我 13812345678"}, {"content": "重复"}, {"content": "重复"}],
            ensure_ascii=False,
        ).encode("utf-8")
        resp = client.post(
            "/api/pipeline/upload",
            files={"file": ("records.json", payload, "application/json")},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["masked_total"], 2)  # 1 条重复被去重
        self.assertIn("138****5678", body["masked"][0]["content"])

    def test_upload_rejects_bad_suffix(self):
        resp = client.post(
            "/api/pipeline/upload",
            files={"file": ("evil.txt", b"whatever", "text/plain")},
        )
        self.assertEqual(resp.status_code, 400)

    def test_run_with_records(self):
        resp = client.post(
            "/api/pipeline/run",
            json={"records": [{"content": "邮箱 test@example.com"}]},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(resp.json()["report"]["mask_hits"].get("email", 0), 1)


if __name__ == "__main__":
    unittest.main()
