"""对比评测 —— 2 种意图方式（单模型A / 双模型B）× 2 种融合方式（RRF / MinMax）

评测 4 种配置组合：
- A-rrf    单模型意图+工具调用 × RRF
- A-minmax 单模型意图+工具调用 × MinMax归一化加权
- B-rrf    小模型意图+指导大模型工具调用 × RRF
- B-minmax 小模型意图+指导大模型工具调用 × MinMax归一化加权

指标：
- source_hit_rate  ：期望来源在最终召回来源中的命中率
- keyword_recall   ：回答包含期望关键词的比例
- intent_hit       ：意图判断与期望意图标签的匹配率（期望意图的召回率）
- passed           ：src>0 且 kw>0
- elapsed          ：单条耗时

支持：--limit 快速验证 / --parallel 并行 / 断点续跑（结果缓存）
"""
import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import rag.tools as tools_mod
from rag.pipeline import query as query_dual
from rag.pipeline import query_single

CONFIGS = {
    "A-rrf":    {"intent_mode": "single", "fusion": "rrf"},
    "A-minmax": {"intent_mode": "single", "fusion": "minmax"},
    "B-rrf":    {"intent_mode": "dual",   "fusion": "rrf"},
    "B-minmax": {"intent_mode": "dual",   "fusion": "minmax"},
}
CFG_LABELS = {
    "A-rrf":    "A·单模型意图 + RRF",
    "A-minmax": "A·单模型意图 + MinMax",
    "B-rrf":    "B·双模型意图 + RRF",
    "B-minmax": "B·双模型意图 + MinMax",
}


def load_queries(path: str) -> List[Dict]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["queries"]


def tools_to_intents(used_tools: List[str]) -> List[str]:
    """工具调用 → 意图集合（方案A无显式意图，从实际调用的工具反推）"""
    ints = set()
    for t in used_tools or []:
        if "vector" in t:
            ints.add("vector")
        if "database" in t:
            ints.add("database")
    return sorted(ints)


def calc_source_hit(question: str, sources: List[Dict], expected: List[str]) -> tuple:
    source_names = [s["source_name"] for s in sources]
    hits, misses = [], []
    for exp in expected:
        if any(exp in name for name in source_names):
            hits.append(exp)
        else:
            misses.append(exp)
    rate = len(hits) / len(expected) if expected else 1.0
    return rate, hits, misses


def calc_keyword_recall(answer: str, expected_keywords: List[str]) -> tuple:
    answer_lower = (answer or "").lower()
    hits, misses = [], []
    for kw in expected_keywords:
        if kw.lower() in answer_lower:
            hits.append(kw)
        else:
            misses.append(kw)
    rate = len(hits) / len(expected_keywords) if expected_keywords else 1.0
    return rate, hits, misses


def calc_intent_hit(expected: List[str], actual: List[str]) -> tuple:
    """期望意图被正确判别的比例"""
    if not expected:
        return 1.0, actual, []
    hits = [e for e in expected if e in actual]
    misses = [e for e in expected if e not in actual]
    return (len(hits) / len(expected)), hits, misses


def run_case(config: str, q: Dict) -> Dict:
    """执行单条用例，返回评测结果（不抛异常）"""
    cfg = CONFIGS[config]
    tools_mod.FUSION_MODE = cfg["fusion"]

    qid = q["id"]
    question = q["question"]
    expected_sources = q.get("expected_sources", [])
    expected_keywords = q.get("expected_keywords", [])
    expected_intents = q.get("expected_intents", [])

    t0 = time.time()
    try:
        if cfg["intent_mode"] == "single":
            result = query_single(question, verbose=False)
            actual_intents = tools_to_intents(result.get("used_tools", []))
            plan = result.get("plan", "single")
        else:
            result = query_dual(question, verbose=False)
            ir = result.get("intent")
            actual_intents = list(ir.intents) if ir else []
            plan = result.get("plan", "?")

        answer = result.get("answer", "") or ""
        sources = result.get("sources", []) or []
        elapsed = time.time() - t0

        src_rate, src_hits, src_misses = calc_source_hit(question, sources, expected_sources)
        kw_rate, kw_hits, kw_misses = calc_keyword_recall(answer, expected_keywords)
        int_rate, int_hits, int_misses = calc_intent_hit(expected_intents, actual_intents)
        passed = src_rate > 0 and kw_rate > 0

        return {
            "config": config, "id": qid, "category": q.get("category", ""),
            "question": question,
            "source_hit_rate": round(src_rate, 3),
            "keyword_recall": round(kw_rate, 3),
            "intent_hit": round(int_rate, 3),
            "passed": passed,
            "plan": plan,
            "actual_intents": actual_intents,
            "used_tools": result.get("used_tools", []),
            "source_hits": src_hits, "source_misses": src_misses,
            "keyword_hits": kw_hits, "keyword_misses": kw_misses,
            "intent_hits": int_hits, "intent_misses": int_misses,
            "elapsed": round(elapsed, 2),
            "answer_preview": answer[:80],
        }
    except Exception as e:
        return {
            "config": config, "id": qid, "category": q.get("category", ""),
            "question": question,
            "source_hit_rate": 0, "keyword_recall": 0, "intent_hit": 0,
            "passed": False, "error": str(e),
            "elapsed": round(time.time() - t0, 2),
            "actual_intents": [], "used_tools": [],
        }


def summarize(results: List[Dict], queries: List[Dict]) -> Dict:
    """按 config 汇总得分"""
    by_cfg: Dict[str, List[Dict]] = {}
    for r in results:
        by_cfg.setdefault(r["config"], []).append(r)

    summary = {}
    for config in CONFIGS:
        rs = by_cfg.get(config, [])
        n = len(rs)
        if n == 0:
            summary[config] = {"total": 0}
            continue
        passed = sum(1 for r in rs if r["passed"])
        summary[config] = {
            "label": CFG_LABELS[config],
            "total": n,
            "passed": passed,
            "failure": n - passed,
            "pass_rate": passed / n,
            "avg_source_hit": sum(r["source_hit_rate"] for r in rs) / n,
            "avg_keyword_recall": sum(r["keyword_recall"] for r in rs) / n,
            "avg_intent_hit": sum(r["intent_hit"] for r in rs) / n,
            "avg_time": sum(r["elapsed"] for r in rs) / n,
            "total_time": round(sum(r["elapsed"] for r in rs), 1),
        }
        # 分类统计
        cats = {}
        for r in rs:
            c = r["category"]
            cats.setdefault(c, {"total": 0, "passed": 0, "src": 0.0, "kw": 0.0, "int": 0.0})
            cats[c]["total"] += 1
            cats[c]["passed"] += 1 if r["passed"] else 0
            cats[c]["src"] += r["source_hit_rate"]
            cats[c]["kw"] += r["keyword_recall"]
            cats[c]["int"] += r["intent_hit"]
        summary[config]["categories"] = cats
    return summary


def print_summary(summary: Dict):
    print(f"\n{'='*84}")
    print(f"{'配置':<22} {'通过':<7} {'通过率':<7} {'来源命中':<8} "
          f"{'关键词':<8} {'意图命中':<8} {'均耗':<6}")
    print("-" * 84)
    for cfg, s in summary.items():
        if "pass_rate" not in s:
            continue
        print(f"{CFG_LABELS[cfg]:<22} {s['passed']}/{s['total']:<4} "
              f"{s['pass_rate']:.1%}   {s['avg_source_hit']:.2f}     "
              f"{s['avg_keyword_recall']:.2f}     {s['avg_intent_hit']:.2f}     "
              f"{s['avg_time']:.1f}s")
    print("=" * 84)


def main():
    ap = argparse.ArgumentParser(description="RAG 对比评测（意图方式 × 融合方式）")
    ap.add_argument("--queries", type=str, default=None, help="用例文件路径")
    ap.add_argument("--configs", type=str, default=",".join(CONFIGS.keys()),
                    help="要运行的配置组合，逗号分隔")
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 条（0=全部）")
    ap.add_argument("--parallel", type=int, default=4, help="并行 worker 数")
    ap.add_argument("--output", type=str, default=None, help="报告 JSON 输出路径")
    ap.add_argument("--resume", action="store_true", help="断点续跑（缓存已有结果）")
    args = ap.parse_args()

    qpath = args.queries or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                         "第一次评测", "eval_compare_queries.json")
    queries = load_queries(qpath)
    if args.limit > 0:
        queries = queries[:args.limit]

    configs = [c.strip() for c in args.configs.split(",") if c.strip() in CONFIGS]
    print(f"用例: {len(queries)} 条 | 配置: {configs} | 并行: {args.parallel}")

    # 缓存文件（断点续跑）
    cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "第一次评测")
    os.makedirs(cache_dir, exist_ok=True)
    cache_path = args.output or os.path.join(cache_dir, "eval_compare_results.json")
    cache = {}
    if args.resume and os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            cache = json.load(f)
        print(f"续跑模式：已缓存 {len(cache)} 条结果")

    todo = []
    for cfg in configs:
        for q in queries:
            key = f"{cfg}|{q['id']}"
            if key not in cache:
                todo.append((cfg, q))
    print(f"待运行: {len(todo)} 条")

    results = list(cache.values())
    if todo:
        def _worker(item):
            cfg, q = item
            return cfg, q["id"], run_case(cfg, q)

        with ThreadPoolExecutor(max_workers=args.parallel) as ex:
            futures = [ex.submit(_worker, item) for item in todo]
            done = 0
            for fut in as_completed(futures):
                cfg, qid, r = fut.result()
                cache[f"{cfg}|{qid}"] = r
                results.append(r)
                done += 1
                if done % 10 == 0 or done == len(todo):
                    # 增量保存缓存，中断后可续跑
                    with open(cache_path, "w", encoding="utf-8") as f:
                        json.dump(cache, f, ensure_ascii=False, indent=1)
                    print(f"  进度: {done}/{len(todo)} (缓存 {len(cache)})", flush=True)

        # 最终缓存
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=1)

    summary = summarize(results, queries)
    print_summary(summary)

    report = {
        "queries_total": len(queries),
        "configs": configs,
        "summary": summary,
        "details": results,
    }
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=1)
        print(f"报告已写入: {args.output}")


if __name__ == "__main__":
    main()
