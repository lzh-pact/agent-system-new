"""向量检索（BR-02.2 / G-2）。

- 配置了 ``embedding_model`` + Key + Base URL 时：走 OpenAI 兼容 ``/embeddings``
  接口生成真实语义向量；
- 未配置时：回退内置「特征哈希词袋向量 + 余弦相似度」，零依赖、确定性、可离线。

后端默认 ``chroma``（若未安装 chromadb 自动回退 ``simple``）；两者共享同一套
embedding 生成逻辑，接口一致，可无缝切换。
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import urllib.error
import urllib.request

from app_core.logger import get_logger
from app_core.models import Chunk

log = get_logger("retrieval.vector")

_EMBED_DIM = 256


def _grams(text: str, n: int):
    return {text[i : i + n] for i in range(len(text) - n + 1)}


def _hash_embed(text: str, dim: int = _EMBED_DIM) -> list[float]:
    """特征哈希词袋向量（L2 归一化），离线兜底用。"""
    vec = [0.0] * dim
    tokens = re.findall(r"[A-Za-z0-9_]+|[一-鿿]", (text or "").lower())
    for tok in tokens:
        for gram in _grams(tok, 1) | _grams(tok, 2) | _grams(tok, 3):
            h = int(hashlib.md5(gram.encode("utf-8")).hexdigest(), 16)  # noqa: S324
            idx = h % dim
            sign = 1.0 if (h >> 8) % 2 == 0 else -1.0
            vec[idx] += sign
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


class _OpenAIEmbedding:
    """OpenAI 兼容 embedding 客户端（仅标准库 urllib）。"""

    def __init__(self, model: str, api_key: str, base_url: str):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/") + "/embeddings"

    def embed(self, text: str) -> list[float]:
        payload = {"model": self.model, "input": [text]}
        req = urllib.request.Request(
            self.base_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 - 用户自配地址
            data = json.loads(resp.read().decode("utf-8"))
        return data["data"][0]["embedding"]


def _make_embedder(config):
    """按配置返回 ``text -> list[float]`` 的 embedding 函数。"""
    if (
        getattr(config, "embedding_model", "")
        and getattr(config, "embedding_api_key", "")
        and getattr(config, "embedding_base_url", "")
    ):
        client = _OpenAIEmbedding(
            config.embedding_model, config.embedding_api_key, config.embedding_base_url
        )
        log.info("使用真实 embedding 模型：%s", config.embedding_model)
        return client.embed
    return _hash_embed


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


class VectorStore:
    """向量存储接口。"""

    def add(self, chunk: Chunk) -> None:
        raise NotImplementedError

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        raise NotImplementedError


class SimpleVectorStore(VectorStore):
    """内存向量存储（零依赖）。"""

    def __init__(self, embed=None):
        self._embed = embed or _hash_embed
        self._meta: dict = {}
        self._vecs: list = []
        self._ids: list = []

    def add(self, chunk: Chunk) -> None:
        vec = self._embed(chunk.text)
        self._meta[chunk.chunk_id] = (chunk.doc_id, chunk.text)
        self._vecs.append(vec)
        self._ids.append(chunk.chunk_id)

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        if not self._vecs:
            return []
        q = self._embed(query)
        pairs = [(_cosine(q, self._vecs[i]), self._ids[i]) for i in range(len(self._vecs))]
        scored = sorted(pairs, key=lambda x: -x[0])[: max(top_k * 2, 1)]
        return [
            {
                "chunk_id": cid,
                "doc_id": self._meta[cid][0],
                "text": self._meta[cid][1],
                "vector_score": max(score, 0.0),
            }
            for score, cid in scored
        ]


class ChromaVectorStore(VectorStore):
    """ChromaDB 持久化后端，接口与 SimpleVectorStore 一致。

    不使用 chromadb 的 EmbeddingFunction 机制（1.x 版本对自定义实现有
    name/config 协议要求），改为 add/query 时显式传 embeddings——
    embedding 统一由本类持有的 ``_embed`` 生成，与后端版本解耦。
    """

    def __init__(self, path: str = "./data/chroma", embed=None):
        import chromadb  # type: ignore

        self._embed = embed or _hash_embed
        self._client = chromadb.PersistentClient(path=path)
        self._collection = self._client.get_or_create_collection(name="knowledge")

    def add(self, chunk: Chunk) -> None:
        # upsert：相同内容 id 原地覆盖，重复入库不累积副本
        self._collection.upsert(
            ids=[chunk.chunk_id],
            documents=[chunk.text],
            metadatas=[{"doc_id": chunk.doc_id, "chunk_id": chunk.chunk_id}],
            embeddings=[self._embed(chunk.text)],
        )

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        res = self._collection.query(
            query_embeddings=[self._embed(query)], n_results=max(top_k * 2, 1)
        )
        out = []
        ids = res["ids"][0]
        docs = res["documents"][0]
        metas = res["metadatas"][0]
        dists = res.get("distances", [[]])[0]
        for i, cid in enumerate(ids):
            meta = metas[i] or {}
            dist = dists[i] if i < len(dists) else 0.0
            score = 1.0 / (1.0 + float(dist)) if dist is not None else 0.0
            out.append({
                "chunk_id": cid,
                "doc_id": meta.get("doc_id", ""),
                "text": docs[i],
                "vector_score": score,
            })
        return out


def get_vector_store(config) -> VectorStore:
    """按配置返回向量后端（默认 chroma，未安装则回退 simple）。"""
    backend = getattr(config, "vector_backend", "chroma")
    embed = _make_embedder(config)
    if backend == "chroma":
        try:
            log.info("使用 ChromaDB 向量后端")
            return ChromaVectorStore(embed=embed)
        except Exception as exc:  # noqa: BLE001
            log.warning("ChromaDB 不可用（%s），回退为 simple 后端", exc)
    return SimpleVectorStore(embed=embed)