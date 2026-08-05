"""RAG Pipeline —— 混合检索 → Reranker → LLM 生成"""
import os
import sys

# 确保从项目根目录 import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.database import SessionLocal
from rag.bm25_index import BM25Index, clean_text
from rag.config import TOP_K_RERANK
from rag.generator import generate
from rag.reranker import rerank
from rag.retriever import hybrid_search
from rag.sql_fallback import enrich


def query(question: str, verbose: bool = True) -> dict:
    """
    完整 RAG 问答流程。
    返回: {"answer": str, "sources": [dict]}
    """
    session = SessionLocal()
    bm25 = BM25Index.load()
    if bm25 is None:
        raise RuntimeError("BM25 索引未构建，请先运行 build_index.py")

    # ---- Phase 1: 混合检索 ----
    candidates = hybrid_search(session, bm25, question)

    if verbose:
        print(f"\n[检索] 召回 {len(candidates)} 条候选")
        for i, c in enumerate(candidates[:5]):
            print(f"  {i+1}. [{c['source_name']}][{c['chunk_type']}] "
                  f"bm25={c['bm25_score']:.3f} vec={c['vector_score']:.3f} "
                  f"combined={c['combined_score']:.3f}")

    # ---- Phase 2: Reranker ----
    documents = [c["content"] for c in candidates]
    reranked = rerank(question, documents, top_k=TOP_K_RERANK)

    if verbose:
        print(f"\n[Reranker] 重排后 Top {len(reranked)}:")
        for i, r in enumerate(reranked):
            orig = candidates[r["index"]]
            print(f"  {i+1}. [{orig['source_name']}][{orig['chunk_type']}] "
                  f"score={r['score']:.4f}")

    # ---- Phase 3: LLM 生成 ----
    top_contexts = []
    for r in reranked:
        orig = candidates[r["index"]]
        text = clean_text(r["document"])
        src_name = orig.get("source_name", "未知")
        chunk_type = orig.get("chunk_type", "")
        top_contexts.append(f"[{src_name}][{chunk_type}] {text}")

    # ---- Phase 2.5: SQL Fallback ----
    supplement_texts = enrich(question, top_contexts)
    if verbose and supplement_texts:
        print(f"\n[SQL] 补充了 {len(supplement_texts)} 条结构化数据")
        for s in supplement_texts[:5]:
            print(f"  + {s[:100]}...")

    # ---- Phase 3: LLM 生成 ----
    # SQL 补全也可能带 wiki 标记，统一清洗后再拼接
    supplement_texts = [clean_text(s) for s in supplement_texts]
    full_contexts = supplement_texts + top_contexts
    answer = generate(question, full_contexts)

    # 构建引用来源
    sources = []
    for r in reranked:
        orig = candidates[r["index"]]
        sources.append({
            "source_name": orig["source_name"],
            "source_type": orig.get("source_type", "unknown"),
            "chunk_type": orig["chunk_type"],
            "content": clean_text(r["document"])[:200],
            "rerank_score": r["score"],
        })

    session.close()
    return {"answer": answer, "sources": sources}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="ENDfield RAG 问答")
    parser.add_argument("question", nargs="?", help="问题")
    parser.add_argument("--no-verbose", action="store_true", help="关闭检索详情")
    args = parser.parse_args()

    if args.question:
        result = query(args.question, verbose=not args.no_verbose)
        print(f"\n{'='*60}")
        print(f"[回答]\n{result['answer']}")
        print(f"\n[来源]")
        for s in result["sources"]:
            print(f"  - [{s['source_name']}] ({s['chunk_type']}) "
                  f"rerank={s['rerank_score']:.4f}")
    else:
        print("ENDfield RAG 问答 (交互模式)")
        print("输入 'exit' 退出\n")
        while True:
            q = input("> ").strip()
            if q.lower() in ("exit", "quit", "q"):
                break
            if not q:
                continue
            try:
                result = query(q, verbose=True)
                print(f"\n[回答]\n{result['answer']}\n")
            except Exception as e:
                print(f"错误: {e}")
