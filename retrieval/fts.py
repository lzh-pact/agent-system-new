"""SQLite-FTS5 全文检索（BR-02.1）。

优先使用 FTS5（bm25 打分），并显式按「中文逐字 / 英文逐词」分词后写入，
避免不同 SQLite 构建对 CJK 默认分词的差异；若环境未启用 FTS5 则回退为
内存倒排索引打分，保证任何环境都能跑通。
"""
from __future__ import annotations

import re
import sqlite3
from collections import defaultdict
from pathlib import Path

from app_core.logger import get_logger
from app_core.models import Chunk

log = get_logger("retrieval.fts")


class FTSIndex:
    def __init__(self, db_path: str | Path = ":memory:"):
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS chunks "
            "(doc_id TEXT, chunk_id TEXT, text TEXT)"
        )
        if self._supports_fts5():
            self.backend = "fts5"
            self.conn.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts "
                "USING fts5(doc_id, chunk_id, text)"
            )
        else:
            self.backend = "inverted"
            self._index: dict = defaultdict(list)
            log.warning("当前 SQLite 未启用 FTS5，回退为倒排索引检索")

    def _supports_fts5(self) -> bool:
        try:
            self.conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS _probe USING fts5(x)")
            self.conn.execute("DROP TABLE _probe")
            return True
        except sqlite3.OperationalError:
            return False

    def add(self, chunk: Chunk) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO chunks(doc_id, chunk_id, text) VALUES (?,?,?)",
            (chunk.doc_id, chunk.chunk_id, chunk.text),
        )
        if self.backend == "fts5":
            # 显式空格分词，让 unicode61 按 token 建索引，中文逐字可检索
            tokenized = " ".join(_tokens(chunk.text))
            self.conn.execute(
                "INSERT INTO chunks_fts(doc_id, chunk_id, text) VALUES (?,?,?)",
                (chunk.doc_id, chunk.chunk_id, tokenized),
            )
        else:
            for token in _tokens(chunk.text):
                self._index[token].append(chunk)

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        if self.backend == "fts5":
            return self._search_fts5(query, top_k)
        return self._search_inverted(query, top_k)

    def _search_fts5(self, query: str, top_k: int) -> list[dict]:
        tokens = _tokens(query)
        if not tokens:
            return []
        terms = " OR ".join(f'"{t}"' for t in tokens)
        rows = self.conn.execute(
            "SELECT c.doc_id, c.chunk_id, c.text, bm25(chunks_fts) AS r "
            "FROM chunks_fts JOIN chunks c ON c.chunk_id = chunks_fts.chunk_id "
            "WHERE chunks_fts MATCH ? ORDER BY r LIMIT ?",
            (terms, top_k * 2),
        ).fetchall()
        # bm25 越小越相关（负值越负越相关），取相反数转成越大越相关
        return [
            {"chunk_id": r[1], "doc_id": r[0], "text": r[2],
             "fts_score": -float(r[3])}
            for r in rows
        ]

    def _search_inverted(self, query: str, top_k: int) -> list[dict]:
        tokens = _tokens(query)
        if not tokens:
            return []
        scores: dict = defaultdict(float)
        meta: dict = {}
        for token in tokens:
            for chunk in self._index.get(token, []):
                scores[chunk.chunk_id] += 1.0
                meta[chunk.chunk_id] = chunk
        ranked = sorted(scores.items(), key=lambda kv: -kv[1])[: top_k * 2]
        return [
            {"chunk_id": cid, "doc_id": meta[cid].doc_id,
             "text": meta[cid].text, "fts_score": score}
            for cid, score in ranked
        ]


def _tokens(text: str) -> list[str]:
    """中英文混合分词：连续英文/数字为一个 token，中文逐字为 token。"""
    return re.findall(r"[A-Za-z0-9_]+|[一-鿿]", (text or "").lower())