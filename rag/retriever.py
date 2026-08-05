"""混合检索器 —— RRF（Reciprocal Rank Fusion）融合 BM25 与 pgvector 排名"""
from sqlalchemy.orm import Session

from db.models import Enemy, Equipment, KnowledgeChunk, Operator, Weapon
from rag.bm25_index import BM25Index
from rag.embedder import query_embed
from rag.config import TOP_K_RETRIEVAL, RRF_K


def hybrid_search(
    session: Session,
    bm25: BM25Index,
    query: str,
    top_k: int = TOP_K_RETRIEVAL,
) -> list[dict]:
    """
    RRF 融合检索：分别取 BM25 与 pgvector 的排名，按 1/(k+rank) 相加融合。
    返回: [{"chunk_id": int, "content": str, "source_name": str,
            "source_type": str, "chunk_type": str, "bm25_score": float,
            "vector_score": float, "combined_score": float}, ...]
    """
    # ---- BM25 检索（按分降序 → 排名）----
    bm25_results = bm25.search(query, top_k=top_k)
    bm25_scores = {cid: score for cid, score in bm25_results}
    bm25_rank = {cid: i + 1 for i, (cid, _) in enumerate(bm25_results)}
    candidate_ids = set(bm25_scores.keys())

    # ---- pgvector 余弦相似度检索（按相似度降序 → 排名）----
    q_embedding = query_embed(query)
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
    vector_rank = {}
    chunk_map = {}
    for i, (chunk, sim) in enumerate(vector_rows):
        vector_scores[chunk.id] = float(sim)
        vector_rank[chunk.id] = i + 1
        candidate_ids.add(chunk.id)
        chunk_map[chunk.id] = {
            "chunk_id": chunk.id,
            "content": chunk.content,
            "chunk_type": chunk.chunk_type,
            "operator_id": chunk.operator_id,
            "weapon_id": chunk.weapon_id,
            "enemy_id": chunk.enemy_id,
            "equipment_id": chunk.equipment_id,
        }

    # 补充 BM25 独有的 chunk
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
                "weapon_id": c.weapon_id,
                "enemy_id": c.enemy_id,
                "equipment_id": c.equipment_id,
            }

    # ---- RRF 融合：1/(k+rank_bm25) + 1/(k+rank_vector) ----
    rrf_scores = {}
    for cid in candidate_ids:
        s = 0.0
        if cid in bm25_rank:
            s += 1.0 / (RRF_K + bm25_rank[cid])
        if cid in vector_rank:
            s += 1.0 / (RRF_K + vector_rank[cid])
        rrf_scores[cid] = s

    results = []
    for cid in candidate_ids:
        entry = chunk_map.get(cid)
        if entry:
            entry["bm25_score"] = bm25_scores.get(cid, 0.0)
            entry["vector_score"] = vector_scores.get(cid, 0.0)
            entry["combined_score"] = rrf_scores[cid]  # RRF 融合分数
            entry["rrf_score"] = rrf_scores[cid]
            results.append(entry)

    results.sort(key=lambda x: x["combined_score"], reverse=True)
    top_results = results[:top_k]

    # 补充来源名称（干员 / 武器 / 敌人 / 装备）
    op_ids = {r["operator_id"] for r in top_results if r.get("operator_id")}
    wp_ids = {r["weapon_id"] for r in top_results if r.get("weapon_id")}
    en_ids = {r["enemy_id"] for r in top_results if r.get("enemy_id")}
    eq_ids = {r["equipment_id"] for r in top_results if r.get("equipment_id")}

    op_names = {}
    if op_ids:
        op_names = {
            o.article_id: o.name
            for o in session.query(Operator).filter(Operator.article_id.in_(op_ids)).all()
        }
    wp_names = {}
    if wp_ids:
        wp_names = {
            w.article_id: w.name
            for w in session.query(Weapon).filter(Weapon.article_id.in_(wp_ids)).all()
        }
    en_names = {}
    if en_ids:
        en_names = {
            e.article_id: e.name
            for e in session.query(Enemy).filter(Enemy.article_id.in_(en_ids)).all()
        }
    eq_names = {}
    if eq_ids:
        eq_names = {
            q.article_id: q.name
            for q in session.query(Equipment).filter(Equipment.article_id.in_(eq_ids)).all()
        }

    for r in top_results:
        if r.get("operator_id"):
            r["source_name"] = op_names.get(r["operator_id"], "未知干员")
            r["source_type"] = "operator"
        elif r.get("weapon_id"):
            r["source_name"] = wp_names.get(r["weapon_id"], "未知武器")
            r["source_type"] = "weapon"
        elif r.get("enemy_id"):
            r["source_name"] = en_names.get(r["enemy_id"], "未知敌人")
            r["source_type"] = "enemy"
        elif r.get("equipment_id"):
            r["source_name"] = eq_names.get(r["equipment_id"], "未知装备")
            r["source_type"] = "equipment"
        else:
            r["source_name"] = "未知"
            r["source_type"] = "unknown"
        # 兼容旧字段
        r["operator_name"] = r["source_name"]

    return top_results
