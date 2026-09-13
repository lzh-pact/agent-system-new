"""模块 C：混合检索（SQLite-FTS5 全文 + ChromaDB/简单向量，加权融合）。"""
from .chunker import chunk_text, chunk_doc
from .fts import FTSIndex
from .vector import VectorStore, get_vector_store
from .hybrid import HybridRetriever

__all__ = [
    "chunk_text",
    "chunk_doc",
    "FTSIndex",
    "VectorStore",
    "get_vector_store",
    "HybridRetriever",
]