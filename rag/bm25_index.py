"""BM25 索引 —— jieba 分词 + 标记清洗，用于关键词检索"""
import os
import pickle
import re

import numpy as np
from rank_bm25 import BM25Okapi
from sqlalchemy.orm import Session

from db.models import KnowledgeChunk

INDEX_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "data_main", "bm25_index.pkl")

# 清洗 wiki 标记标签（<@ba.key>、<#ba.weak>、{agi}、{ultimate_gain_up:0.0%} 等）
_WIKI_TAG_RE = re.compile(r'<[@#]?[a-zA-Z_.]+>|</>|{[^}]+}')


def clean_text(text: str) -> str:
    """移除 wiki 标记，保留纯中文文本"""
    return _WIKI_TAG_RE.sub('', text)


def tokenize(text: str) -> list[str]:
    """jieba 分词"""
    import jieba
    cleaned = clean_text(text)
    return list(jieba.cut(cleaned))


class BM25Index:
    def __init__(self):
        self.bm25: BM25Okapi = None
        self.chunk_ids: list[int] = []

    def build(self, texts: list[str], chunk_ids: list[int]):
        tokenized = [tokenize(t) for t in texts]
        self.bm25 = BM25Okapi(tokenized)
        self.chunk_ids = chunk_ids

    def search(self, query: str, top_k: int = 30) -> list[tuple[int, float]]:
        """返回 [(chunk_id, bm25_score), ...]"""
        if self.bm25 is None:
            return []
        tokenized = tokenize(query)
        scores = self.bm25.get_scores(tokenized)
        max_score = scores.max()
        if max_score > 0:
            scores = scores / max_score
        top_indices = np.argsort(scores)[::-1][:top_k]
        return [(self.chunk_ids[i], float(scores[i])) for i in top_indices if scores[i] > 0]

    def save(self, path: str = INDEX_PATH):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump({"bm25": self.bm25, "chunk_ids": self.chunk_ids}, f)

    @classmethod
    def load(cls, path: str = INDEX_PATH):
        if not os.path.exists(path):
            return None
        with open(path, "rb") as f:
            data = pickle.load(f)
        idx = cls()
        idx.bm25 = data["bm25"]
        idx.chunk_ids = data["chunk_ids"]
        return idx


def build_bm25(session: Session) -> BM25Index:
    """从数据库 knowledge_chunks 构建 BM25 索引"""
    chunks = session.query(KnowledgeChunk).all()
    texts = [c.content for c in chunks]
    chunk_ids = [c.id for c in chunks]
    bm25 = BM25Index()
    bm25.build(texts, chunk_ids)
    bm25.save()
    print(f"BM25 索引构建完成: {len(texts)} 条切片")
    return bm25
