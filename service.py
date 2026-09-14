"""系统门面：把配置、LLM、检索、两个 Agent 组装成可直接调用的服务。

demo.py 与 frontend 都通过本类复用同一套装配逻辑，避免重复初始化。
"""
from __future__ import annotations

from pathlib import Path

from app_core.config import load_config, get_config, AppConfig
from app_core.llm import LLMClient
from app_core.models import (
    ContentStage,
    GeneratedContent,
    KnowledgeDoc,
    Message,
    MessageRole,
    RetrievedChunk,
    Session,
)
from app_core.session import SessionStore
from data_pipeline.masker import run_pipeline
from retrieval.fts import FTSIndex
from retrieval.hybrid import HybridRetriever
from retrieval.vector import get_vector_store
from agents.content.graph import ContentAgent
from agents.content.persist import Checkpointer
from agents.pre_sale.graph import ReActAgent, AgentAnswer
from agents.pre_sale.tools import Tools, ProductCatalog


class System:
    """智能 AI Agent 售前服务系统的统一入口。"""

    def __init__(self, root: str | Path | None = None):
        self.config: AppConfig = load_config(Path(root) if root else None)
        self.llm = LLMClient(self.config.llm)

        self.fts = FTSIndex(":memory:")
        self.vector = get_vector_store(self.config.retrieval)
        self.retriever = HybridRetriever(
            self.fts,
            self.vector,
            chunk_size=self.config.retrieval.chunk_size,
            overlap=self.config.retrieval.chunk_overlap,
            top_k=self.config.retrieval.top_k,
            fts_weight=self.config.retrieval.fts_weight,
            vector_weight=self.config.retrieval.vector_weight,
        )

        self.tools = Tools(self.retriever, ProductCatalog.sample())
        self.pre_sale = ReActAgent(
            self.llm,
            self.tools,
            max_steps=self.config.agent.max_steps,
            tool_retries=self.config.agent.tool_retries,
        )
        self.content_agent = ContentAgent(
            self.llm, retries=self.config.content.retries, checkpointer=Checkpointer()
        )
        self.sessions = SessionStore()

    # ---- 数据管道 ----
    def process_data(self, records: list[dict]):
        """清洗 → 去重 → PII 脱敏，返回 (脱敏后记录, 脱敏报告)。"""
        return run_pipeline(records)

    # ---- 会话管理（FR-06 / G-4）----
    def create_session(self, user_id: str = "") -> Session:
        return self.sessions.create(user_id)

    def list_sessions(self) -> list[Session]:
        return self.sessions.list()

    def session_history(self, session_id: str) -> list[Message]:
        return self.sessions.history(session_id)

    # ---- 检索 ----
    def ingest_doc(self, title: str, content: str, source: str = "") -> int:
        doc = KnowledgeDoc(title=title, content=content, source=source)
        return self.retriever.ingest(doc)

    def search(self, query: str, top_k: int | None = None) -> list[RetrievedChunk]:
        return self.retriever.search(query, top_k)

    # ---- 售前咨询 ----
    def ask(self, session_id: str, query: str) -> AgentAnswer:
        """售前咨询：记录用户消息，携带会话历史推理，记录回答（G-4 隔离）。"""
        self.sessions.add_message(session_id, MessageRole.USER, query)
        history = [
            {"role": m.role.value, "content": m.content}
            for m in self.sessions.history(session_id)
        ]
        ans = self.pre_sale.run(session_id, query, history=history)
        self.sessions.add_message(
            session_id, MessageRole.ASSISTANT, ans.answer, ans.source_chunks, ans.trace
        )
        return ans

    # ---- 内容生成 ----
    def generate_content(
        self, session_id: str, product_info: dict, stage: str = "all"
    ) -> list[GeneratedContent]:
        return self.content_agent.generate(session_id, product_info, stage)


# 进程内单例，供演示与前端复用
_instance: System | None = None


def get_system() -> System:
    global _instance
    if _instance is None:
        _instance = System()
    return _instance