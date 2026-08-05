"""RAG 系统评测"""
import json
import os
import re
import sys
import time
from typing import List, Dict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rag.generator import client, LLM_MODEL
from rag.pipeline import query as _rag_query


def load_queries(path: str) -> List[Dict]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["queries"]


def calc_source_hit(question: str, sources: List[Dict], expected: List[str]) -> tuple:
    """检查期望来源是否出现在 Top 5 来源中"""
    source_names = [s["source_name"] for s in sources]
    hits = []
    misses = []
    for exp in expected:
        found = any(exp in name for name in source_names)
        if found:
            hits.append(exp)
        else:
            misses.append(exp)
    rate = len(hits) / len(expected) if expected else 1.0
    return rate, hits, misses


def calc_keyword_recall(answer: str, expected_keywords: List[str]) -> tuple:
    """检查期望关键词是否出现在回答中"""
    answer_lower = answer.lower()
    hits = []
    misses = []
    for kw in expected_keywords:
        if kw.lower() in answer_lower:
            hits.append(kw)
        else:
            misses.append(kw)
    rate = len(hits) / len(expected_keywords) if expected_keywords else 1.0
    return rate, hits, misses


def run_eval(queries: List[Dict], verbose: bool = False) -> Dict:
    results = []
    total_source_hit = 0.0
    total_keyword_recall = 0.0
    total_time = 0.0

    for i, q in enumerate(queries):
        qid = q["id"]
        question = q["question"]
        category = q["category"]
        expected_sources = q.get("expected_sources", [])
        expected_keywords = q.get("expected_keywords", [])

        if verbose:
            print(f"\n[{qid}] {question}")

        try:
            t0 = time.time()
            result = _rag_query(question, verbose=False)
            elapsed = time.time() - t0
            total_time += elapsed

            answer = result["answer"]
            sources = result["sources"]

            src_rate, src_hits, src_misses = calc_source_hit(question, sources, expected_sources)
            kw_rate, kw_hits, kw_misses = calc_keyword_recall(answer, expected_keywords)

            total_source_hit += src_rate
            total_keyword_recall += kw_rate

            passed = src_rate > 0 and kw_rate > 0

            results.append({
                "id": qid,
                "category": category,
                "question": question,
                "source_hit_rate": round(src_rate, 2),
                "keyword_recall": round(kw_rate, 2),
                "passed": passed,
                "source_hits": src_hits,
                "source_misses": src_misses,
                "keyword_hits": kw_hits,
                "keyword_misses": kw_misses,
                "answer_preview": answer[:100],
                "elapsed": round(elapsed, 2),
            })

            if verbose:
                src_status = "O" if passed else "X"
                print(f"  [{src_status}] src={src_rate:.0%} kw={kw_rate:.0%} "
                      f"({elapsed:.1f}s)")

        except Exception as e:
            results.append({
                "id": qid, "category": category, "question": question,
                "source_hit_rate": 0, "keyword_recall": 0,
                "passed": False, "error": str(e),
            })
            if verbose:
                print(f"  [X] ERROR: {e}")

    n = len(queries)
    passed = sum(1 for r in results if r["passed"])

    report = {
        "model": LLM_MODEL,
        "total": n,
        "passed": passed,
        "failure": n - passed,
        "pass_rate": f"{passed}/{n}",
        "avg_source_hit": round(total_source_hit / n, 3),
        "avg_keyword_recall": round(total_keyword_recall / n, 3),
        "avg_time": round(total_time / n, 2),
        "total_time": round(total_time, 1),
        "details": results,
    }
    return report


def print_report(report: Dict):
    print(f"\n{'='*60}")
    print(f"模型: {report['model']}")
    print(f"通过率: {report['pass_rate']} ({report['pass_rate']})")
    print(f"平均来源命中: {report['avg_source_hit']:.1%}")
    print(f"平均关键词召回: {report['avg_keyword_recall']:.1%}")
    print(f"平均耗时: {report['avg_time']}s | 总耗时: {report['total_time']}s")
    print(f"{'='*60}")

    # 分类统计
    cats = {}
    for r in report["details"]:
        cat = r["category"]
        if cat not in cats:
            cats[cat] = {"total": 0, "passed": 0, "src": 0.0, "kw": 0.0}
        cats[cat]["total"] += 1
        if r["passed"]:
            cats[cat]["passed"] += 1
        cats[cat]["src"] += r["source_hit_rate"]
        cats[cat]["kw"] += r["keyword_recall"]

    print(f"\n{'类别':<20} {'数量':<5} {'通过':<5} {'来源命中':<10} {'关键词回收':<10}")
    print("-" * 55)
    for cat, stats in sorted(cats.items()):
        n = stats["total"]
        src_pct = f"{stats['src']/n:.0%}"
        kw_pct = f"{stats['kw']/n:.0%}"
        print(f"{cat:<20} {n:<5} {stats['passed']}/{n:<3} "
              f"{src_pct:<10} {kw_pct:<10}")

    # 失败详情
    fails = [r for r in report["details"] if not r["passed"]]
    if fails:
        print(f"\n--- 失败 ({len(fails)} 条) ---")
        for f in fails:
            print(f"  [{f['id']}] {f['question']}")
            if f.get("source_misses"):
                print(f"    来源缺失: {f['source_misses']}")
            if f.get("keyword_misses"):
                print(f"    关键词缺失: {f['keyword_misses']}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--verbose", "-v", action="store_true", help="逐条输出")
    parser.add_argument("--model", type=str, default=None, help="覆盖模型名 (如 deepseek-reasoner)")
    parser.add_argument("--output", "-o", type=str, default=None, help="输出 JSON 报告路径")
    args = parser.parse_args()

    # 覆盖生成模型
    if args.model:
        import rag.generator as gen_mod
        gen_mod.LLM_MODEL = args.model
        print(f"使用模型: {args.model}")
    else:
        print(f"使用模型: {LLM_MODEL}")

    qfile = os.path.join(os.path.dirname(__file__), "eval_queries.json")
    queries = load_queries(qfile)
    print(f"加载 {len(queries)} 条评测 query")

    report = run_eval(queries, verbose=args.verbose)
    print_report(report)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"\n报告已写入: {args.output}")
