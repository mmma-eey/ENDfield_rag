"""混合检索器 —— RRF / MinMax 归一化加权两种融合方式

- RRF（Reciprocal Rank Fusion）：1/(k+rank_bm25) + 1/(k+rank_vector)，按排名融合
- MinMax：bm25/vector 原始分数各自 min-max 归一化到 [0,1] 后按权重加权求和
"""
from sqlalchemy.orm import Session

from db.models import Enemy, Equipment, KnowledgeChunk, Operator, Weapon
from rag.bm25_index import BM25Index
from rag.embedder import query_embed
from rag.config import BM25_WEIGHT, TOP_K_RETRIEVAL, RRF_K

FUSION_RRF = "rrf"
FUSION_MINMAX = "minmax"


def _rrf_fuse(bm25_rank: dict, vector_rank: dict, candidate_ids: set,
              bm25_scores: dict, vector_scores: dict) -> dict:
    """RRF 融合：1/(k+rank_bm25) + 1/(k+rank_vector)"""
    scores = {}
    for cid in candidate_ids:
        s = 0.0
        if cid in bm25_rank:
            s += 1.0 / (RRF_K + bm25_rank[cid])
        if cid in vector_rank:
            s += 1.0 / (RRF_K + vector_rank[cid])
        scores[cid] = s
    return scores


def _minmax_fuse(bm25_rank: dict, vector_rank: dict, candidate_ids: set,
                 bm25_scores: dict, vector_scores: dict) -> dict:
    """MinMax 归一化加权融合：各子检索内部 min-max 归一化后按 BM25_WEIGHT 加权"""
    def _norm(scores: dict, rank: dict, cids: set) -> dict:
        vals = [scores[c] for c in cids if c in rank]
        if not vals:
            return {c: 0.0 for c in cids}
        lo, hi = min(vals), max(vals)
        out = {}
        for c in cids:
            if c not in rank:
                out[c] = 0.0
            elif hi > lo:
                out[c] = (scores[c] - lo) / (hi - lo)
            else:
                out[c] = 1.0 if scores[c] > 0 else 0.0
        return out

    bm25_norm = _norm(bm25_scores, bm25_rank, candidate_ids)
    vec_norm = _norm(vector_scores, vector_rank, candidate_ids)
    return {
        cid: BM25_WEIGHT * bm25_norm[cid] + (1.0 - BM25_WEIGHT) * vec_norm[cid]
        for cid in candidate_ids
    }


_FUSERS = {FUSION_RRF: _rrf_fuse, FUSION_MINMAX: _minmax_fuse}


def hybrid_search(
    session: Session,
    bm25: BM25Index,
    query: str,
    top_k: int = TOP_K_RETRIEVAL,
    fusion: str = FUSION_RRF,
) -> list[dict]:
    """
    融合检索：分别取 BM25 与 pgvector 的排名/分数，按指定方式融合。
    - fusion="rrf"   : RRF 排名融合 1/(k+rank)
    - fusion="minmax": MinMax 归一化加权（bm25/vector 各自 min-max 归一化后加权）
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

    # ---- 融合：RRF 或 MinMax 归一化加权 ----
    fuse_fn = _FUSERS.get(fusion, _rrf_fuse)
    combined = fuse_fn(bm25_rank, vector_rank, candidate_ids,
                       bm25_scores, vector_scores)

    results = []
    for cid in candidate_ids:
        entry = chunk_map.get(cid)
        if entry:
            entry["bm25_score"] = bm25_scores.get(cid, 0.0)
            entry["vector_score"] = vector_scores.get(cid, 0.0)
            entry["combined_score"] = combined[cid]  # 融合分数
            entry["rrf_score"] = combined[cid]
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
