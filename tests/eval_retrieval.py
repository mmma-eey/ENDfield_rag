"""检索层评测 —— RRF vs MinMax 归一化加权 的召回差异（不调用 LLM 生成）

对每条用例执行一次混合检索（候选集），分别按 RRF / MinMax 排序取 Top5，
比较期望来源的命中率（source_hit@5），量化两种融合方式的召回差异。

注意：单次检索即可同时算两种融合（BM25/向量原始分数已包含在结果中），
因此 embedding 调用量减半。
"""
import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.database import SessionLocal
from rag.bm25_index import BM25Index
from rag.retriever import FUSION_MINMAX, FUSION_RRF, hybrid_search

CFG_LABELS = {
    FUSION_RRF: "RRF 排名融合",
    FUSION_MINMAX: "MinMax 归一化加权",
}


def _top5_sources(candidates, rank_scores: dict) -> list:
    """按融合分数取 Top5，返回 source_name 列表"""
    top = sorted(candidates, key=lambda c: rank_scores.get(c["chunk_id"], 0.0),
                 reverse=True)[:5]
    return [c["source_name"] for c in top]


def calc_hit(names: list, expected: list) -> tuple:
    hits = [e for e in expected if any(e in n for n in names)]
    misses = [e for e in expected if e not in hits]
    rate = len(hits) / len(expected) if expected else 1.0
    return rate, hits, misses


def run_case(q: dict) -> dict:
    session = SessionLocal()
    try:
        bm25 = BM25Index.load()
        t0 = time.time()
        candidates = hybrid_search(session, bm25, q["question"],
                                   top_k=30, fusion=FUSION_RRF)
        elapsed = time.time() - t0

        # 由候选分数重建两种融合排序
        bm25_scores = {c["chunk_id"]: c["bm25_score"] for c in candidates}
        vec_scores = {c["chunk_id"]: c["vector_score"] for c in candidates}
        cids = set(c["chunk_id"] for c in candidates)

        bm25_rank = {c["chunk_id"]: i + 1 for i, c in enumerate(
            sorted(candidates, key=lambda x: -x["bm25_score"]))}
        vec_rank = {c["chunk_id"]: i + 1 for i, c in enumerate(
            sorted(candidates, key=lambda x: -x["vector_score"]))}

        from rag.retriever import _minmax_fuse, _rrf_fuse
        rrf_scores = _rrf_fuse(bm25_rank, vec_rank, cids, bm25_scores, vec_scores)
        minmax_scores = _minmax_fuse(bm25_rank, vec_rank, cids, bm25_scores, vec_scores)

        expected = q.get("expected_sources", [])
        rrf_top5 = _top5_sources(candidates, rrf_scores)
        minmax_top5 = _top5_sources(candidates, minmax_scores)

        rrf_rate, rrf_hits, rrf_misses = calc_hit(rrf_top5, expected)
        mm_rate, mm_hits, mm_misses = calc_hit(minmax_top5, expected)

        return {
            "id": q["id"], "category": q.get("category", ""),
            "question": q["question"],
            "expected_sources": expected,
            "rrf_source_hit": round(rrf_rate, 3), "rrf_top5": rrf_top5,
            "rrf_hits": rrf_hits, "rrf_misses": rrf_misses,
            "minmax_source_hit": round(mm_rate, 3), "minmax_top5": minmax_top5,
            "minmax_hits": mm_hits, "minmax_misses": mm_misses,
            "n_candidates": len(candidates),
            "elapsed": round(elapsed, 2),
        }
    except Exception as e:
        return {"id": q["id"], "category": q.get("category", ""),
                "question": q["question"], "error": str(e)}
    finally:
        session.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--queries", type=str, default=None)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--parallel", type=int, default=6)
    ap.add_argument("--output", type=str, default=None)
    args = ap.parse_args()

    qpath = args.queries or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                         "第一次评测", "eval_compare_queries.json")
    with open(qpath, "r", encoding="utf-8") as f:
        queries = json.load(f)["queries"]
    if args.limit > 0:
        queries = queries[:args.limit]
    print(f"检索层评测：{len(queries)} 条用例 | 并行 {args.parallel}")

    results = []
    with ThreadPoolExecutor(max_workers=args.parallel) as ex:
        futures = [ex.submit(run_case, q) for q in queries]
        for i, fut in enumerate(as_completed(futures), 1):
            results.append(fut.result())
            if i % 40 == 0 or i == len(queries):
                print(f"  进度: {i}/{len(queries)}")

    # 汇总
    n = len(results)
    ok = [r for r in results if "error" not in r]
    rrf_avg = sum(r["rrf_source_hit"] for r in ok) / len(ok)
    mm_avg = sum(r["minmax_source_hit"] for r in ok) / len(ok)
    rrf_win = sum(1 for r in ok if r["rrf_source_hit"] > r["minmax_source_hit"])
    mm_win = sum(1 for r in ok if r["minmax_source_hit"] > r["rrf_source_hit"])
    tie = sum(1 for r in ok if r["rrf_source_hit"] == r["minmax_source_hit"])

    report = {
        "total": n,
        "avg_source_hit": {"rrf": round(rrf_avg, 4), "minmax": round(mm_avg, 4)},
        "win_count": {"rrf": rrf_win, "minmax": mm_win, "tie": tie},
        "categories": {},
        "details": results,
    }
    # 分类统计
    cats = {}
    for r in ok:
        c = r["category"]
        cats.setdefault(c, {"total": 0, "rrf_src": 0.0, "minmax_src": 0.0,
                            "rrf_win": 0, "minmax_win": 0, "tie": 0})
        cats[c]["total"] += 1
        cats[c]["rrf_src"] += r["rrf_source_hit"]
        cats[c]["minmax_src"] += r["minmax_source_hit"]
        if r["rrf_source_hit"] > r["minmax_source_hit"]:
            cats[c]["rrf_win"] += 1
        elif r["minmax_source_hit"] > r["rrf_source_hit"]:
            cats[c]["minmax_win"] += 1
        else:
            cats[c]["tie"] += 1
    for c, st in cats.items():
        st["rrf_avg"] = round(st.pop("rrf_src") / st["total"], 3)
        st["minmax_avg"] = round(st.pop("minmax_src") / st["total"], 3)
    report["categories"] = cats

    # 打印
    print(f"\n{'='*70}")
    print(f"检索召回对比（Top5 来源命中率）: {n} 条")
    print(f"  RRF   平均 source_hit = {rrf_avg:.3f}")
    print(f"  MinMax平均 source_hit = {mm_avg:.3f}")
    print(f"  RRF 胜 {rrf_win}  / MinMax 胜 {mm_win} / 平局 {tie}")
    print(f"{'='*70}")
    print(f"\n{'类别':<18} {'n':<4} {'RRF':<7} {'MinMax':<8} {'RRF胜':<5} {'MinMax胜':<6} {'平'}")
    print("-" * 60)
    for c, st in sorted(cats.items()):
        print(f"{c:<18} {st['total']:<4} {st['rrf_avg']:.3f}  {st['minmax_avg']:.3f}  "
              f"{st['rrf_win']:<5} {st['minmax_win']:<6} {st['tie']}")

    if args.output:
        os.makedirs(os.path.dirname(args.output), exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=1)
        print(f"\n报告已写入: {args.output}")


if __name__ == "__main__":
    main()
