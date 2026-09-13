"""文档切片（BR-02.3）：滑动窗口，chunk_size / overlap 可配。"""
from __future__ import annotations

import hashlib

from app_core.models import Chunk, KnowledgeDoc


def chunk_text(text: str, chunk_size: int = 512, overlap: int = 64) -> list[str]:
    """把长文本按字符滑动窗口切分。"""
    text = text.strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]
    step = max(chunk_size - overlap, 1)
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start += step
    return chunks


def chunk_doc(
    doc: KnowledgeDoc, chunk_size: int = 512, overlap: int = 64
) -> list[Chunk]:
    """把文档切成带元信息的 Chunk 列表（标题并入切片，使标题可检索）。"""
    pieces = chunk_text(f"{doc.title}\n{doc.content}", chunk_size, overlap)
    return [
        Chunk(
            text=piece,
            doc_id=doc.doc_id,
            # 内容决定论 id：同一文档重复入库时向量后端可按 id 覆盖（upsert），
            # 避免持久化存储累积随机 uuid 副本污染检索结果
            chunk_id=hashlib.md5(
                f"{doc.title}|{i}|{piece}".encode("utf-8")
            ).hexdigest(),  # noqa: S324 - 非安全场景，仅作内容寻址
            chunk_index=i,
            chunk_size=chunk_size,
            overlap=overlap,
        )
        for i, piece in enumerate(pieces)
    ]