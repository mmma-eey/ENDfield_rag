"""DashScope Embedding —— 文本 → 向量写入 pgvector"""
import time
from typing import List

from dashscope import TextEmbedding
from sqlalchemy.orm import Session

from rag.config import DASHSCOPE_API_KEY, EMBEDDING_MODEL


def embed_batch(texts: List[str], batch_size: int = 10) -> List[List[float]]:
    """批量调用 DashScope Embedding API。每次最多 10 条。"""
    all_embeddings = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        resp = TextEmbedding.call(
            model=EMBEDDING_MODEL,
            input=batch,
            api_key=DASHSCOPE_API_KEY,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Embedding API error: {resp.code} - {resp.message}")

        for item in resp.output["embeddings"]:
            all_embeddings.append(item["embedding"])

        if i + batch_size < len(texts):
            time.sleep(0.3)

    return all_embeddings


def populate_embeddings(session: Session, batch_size: int = 10):
    """读取 knowledge_chunks 中 embedding 为 NULL 的行，调用 DashScope 填充向量。"""
    from db.models import KnowledgeChunk

    chunks = (
        session.query(KnowledgeChunk)
        .filter(KnowledgeChunk.embedding.is_(None))
        .all()
    )
    if not chunks:
        print("所有切片已有向量，无需填充")
        return

    print(f"待嵌入切片: {len(chunks)} 条")
    texts = [c.content for c in chunks]
    embeddings = embed_batch(texts, batch_size=batch_size)

    for chunk, emb in zip(chunks, embeddings):
        chunk.embedding = emb

    session.commit()
    print(f"向量写入完成: {len(chunks)} 条")


def query_embed(query: str) -> List[float]:
    """单条查询文本 → 向量"""
    resp = TextEmbedding.call(
        model=EMBEDDING_MODEL,
        input=[query],
        api_key=DASHSCOPE_API_KEY,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Embedding API error: {resp.code} - {resp.message}")
    return resp.output["embeddings"][0]["embedding"]
