"""DashScope Reranker —— Qwen 重排模型"""
from typing import List

from dashscope import TextReRank

from rag.config import DASHSCOPE_API_KEY, RERANKER_MODEL


def rerank(query: str, documents: List[str], top_k: int = 5) -> List[dict]:
    """
    调用 DashScope Reranker，对候选文档重新排序。
    返回: [{"index": int, "score": float, "document": str}, ...]  按 score 降序
    """
    if not documents:
        return []

    resp = TextReRank.call(
        model=RERANKER_MODEL,
        query=query,
        documents=documents,
        top_n=min(top_k, len(documents)),
        api_key=DASHSCOPE_API_KEY,
    )

    if resp.status_code != 200:
        raise RuntimeError(f"Reranker API error: {resp.code} - {resp.message}")

    results = resp.output.get("results", [])
    out = []
    for r in results:
        idx = r.get("index", 0)
        out.append({
            "index": idx,
            "score": r.get("relevance_score", 0),
            "document": documents[idx] if idx < len(documents) else "",
        })

    return sorted(out, key=lambda x: x["score"], reverse=True)
