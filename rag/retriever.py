"""混合检索器 —— BM25 + pgvector Cosine 加权融合"""
from sqlalchemy.orm import Session

from db.models import KnowledgeChunk, Operator
from rag.bm25_index import BM25Index
from rag.embedder import query_embed
from rag.config import BM25_WEIGHT, TOP_K_RETRIEVAL


def hybrid_search(
    session: Session,
    bm25: BM25Index,
    query: str,
    top_k: int = TOP_K_RETRIEVAL,
    bm25_weight: float = BM25_WEIGHT,
) -> list[dict]:
    """
    BM25 + Cosine 加权融合检索。
    返回: [{"chunk_id": int, "content": str, "operator_name": str,
            "chunk_type": str, "bm25_score": float, "vector_score": float,
            "combined_score": float}, ...]  按 combined_score 降序
    """
    vector_weight = 1 - bm25_weight

    # ---- BM25 检索 ----
    bm25_results = bm25.search(query, top_k=top_k)
    bm25_scores = {cid: score for cid, score in bm25_results}
    candidate_ids = set(bm25_scores.keys())

    # ---- pgvector 余弦相似度检索 ----
    q_embedding = query_embed(query)
    # pgvector: cosine_distance(embedding, query_vec) → 值越小越相似
    # 余弦相似度 = 1 - cosine_distance
    vector_rows = (
        session.query(
            KnowledgeChunk,
            1 - KnowledgeChunk.embedding.cosine_distance(q_embedding)
        )
        .filter(KnowledgeChunk.embedding.isnot(None))
        .order_by(KnowledgeChunk.embedding.cosine_distance(q_embedding))
        .limit(top_k)
        .all()
    )

    vector_scores = {}
    chunk_map = {}
    for chunk, sim in vector_rows:
        vector_scores[chunk.id] = float(sim)
        candidate_ids.add(chunk.id)
        chunk_map[chunk.id] = {
            "chunk_id": chunk.id,
            "content": chunk.content,
            "chunk_type": chunk.chunk_type,
            "operator_id": chunk.operator_id,
        }

    # 补充 BM25 独有的 chunk（不在 vector 结果中）
    missing_ids = candidate_ids - set(chunk_map.keys())
    if missing_ids:
        extra_chunks = (
            session.query(KnowledgeChunk)
            .filter(KnowledgeChunk.id.in_(missing_ids))
            .all()
        )
        for c in extra_chunks:
            chunk_map[c.id] = {
                "chunk_id": c.id,
                "content": c.content,
                "chunk_type": c.chunk_type,
                "operator_id": c.operator_id,
            }

    # 融合分数
    results = []
    for cid in candidate_ids:
        bm25_s = bm25_scores.get(cid, 0.0)
        vec_s = vector_scores.get(cid, 0.0)
        combined = bm25_weight * bm25_s + vector_weight * vec_s
        entry = chunk_map.get(cid)
        if entry:
            entry["bm25_score"] = bm25_s
            entry["vector_score"] = vec_s
            entry["combined_score"] = combined
            results.append(entry)

    results.sort(key=lambda x: x["combined_score"], reverse=True)
    top_results = results[:top_k]

    # 补充干员名称
    op_ids = {r["operator_id"] for r in top_results}
    ops = {
        o.article_id: o.name
        for o in session.query(Operator).filter(Operator.article_id.in_(op_ids)).all()
    }
    for r in top_results:
        r["operator_name"] = ops.get(r["operator_id"], "未知")

    return top_results
