"""RAG Pipeline —— 意图识别 → 路由分发 → 向量/数据库/大模型Tool Calling → 生成

新架构流程：
1. 小模型（DeepSeek）判断问题意图：vector（向量查询）/ database（数据库查询）/ 两者兼有
2. 路由系统按意图分发：
   - 向量路由    → vector_search 检索 + SQL 补全 + 生成（单一意图快速路径）
   - 数据库路由  → database_query 结构化查询 + 生成（单一意图快速路径）
   - 混合路由    → 大模型 Tool Calling 编排（agent），小模型意图指导大模型调用工具
"""
import os
import sys

# 确保从项目根目录 import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rag.agent import agent_query
from rag.bm25_index import clean_text
from rag.config import TOP_K_RERANK
from rag.db_query import NO_DATA_MSG, field_query_entities, find_entities, query_database
from rag.generator import generate
from rag.intent import classify_intent
from rag.router import PLAN_DATABASE, PLAN_HYBRID, decide_route
from rag.sql_fallback import enrich
from rag.tools import get_runtime, reset_runtime, vector_search


def _run_vector_flow(question: str, verbose: bool = True) -> dict:
    """向量路由：vector_search 检索 → Rerank → SQL 结构化补全 → 生成"""
    reset_runtime()
    vector_search.invoke({"question": question, "top_k": TOP_K_RERANK})
    runtime = get_runtime()
    top_contexts = runtime.vector_contexts

    if verbose:
        print(f"\n[向量检索] 召回 Top {len(runtime.sources)}")
        for i, s in enumerate(runtime.sources[:5]):
            print(f"  {i+1}. [{s['source_name']}][{s['chunk_type']}] "
                  f"rerank={s['rerank_score']:.4f}")

    if not top_contexts:
        raise RuntimeError("向量检索未返回结果")

    # SQL Fallback：按上下文中实体名补充结构化数据
    supplement_texts = enrich(question, top_contexts)
    if verbose and supplement_texts:
        print(f"\n[SQL] 补充了 {len(supplement_texts)} 条结构化数据")
        for s in supplement_texts[:5]:
            print(f"  + {clean_text(s)[:100]}...")

    # SQL 补全也可能带 wiki 标记，统一清洗后再拼接
    supplement_texts = [clean_text(s) for s in supplement_texts]
    full_contexts = supplement_texts + top_contexts
    answer = generate(question, full_contexts)

    return {"answer": answer, "sources": runtime.sources}


def _run_database_flow(question: str, verbose: bool = True) -> dict:
    """数据库路由：结构化查询 → 生成；未命中实体时回退到向量检索"""
    text = query_database(question)
    if verbose:
        print(f"\n[数据库] 结构化查询 {len(text)} 字符")

    entities = find_entities([question])
    # 字段查询（列表类）命中的实体也要计入来源，供引用/评测
    if not any(entities.values()):
        entities = field_query_entities(question)
    if verbose and entities:
        hits = {k: v for k, v in entities.items() if v}
        if hits:
            print(f"  [数据库] 命中实体: {hits}")

    # 未命中实体 → 回退向量检索（安全路径）
    if text == NO_DATA_MSG:
        if verbose:
            print("  [数据库] 无命中实体，回退向量检索")
        return _run_vector_flow(question, verbose)

    contexts = [clean_text(s) for s in text.split("\n") if s.strip()]
    answer = generate(question, contexts)

    # 构建结构化来源（供引用/评测）
    sources = [
        {"source_name": name, "source_type": ent_type,
         "chunk_type": "database", "content": "", "rerank_score": 0.0}
        for ent_type, names in entities.items()
        for name in names
    ]
    return {"answer": answer, "sources": sources}


def query(question: str, verbose: bool = True) -> dict:
    """完整问答流程（方案B：小模型意图判断 + 指导大模型调用工具）。

    返回: {"answer", "sources", "intent", "plan"}（plan 为路由计划）
    """
    # ---- Phase 0: 小模型意图判断 ----
    intent_result = classify_intent(question)
    if verbose:
        print(f"[意图] {intent_result.intents} | {intent_result.reason or '识别成功'}")

    # ---- Phase 1: 路由分发 ----
    decision = decide_route(intent_result.intents)
    if verbose:
        print(f"[路由] {decision.describe()}")

    if decision.plan == PLAN_DATABASE:
        result = _run_database_flow(question, verbose)
    elif decision.plan == PLAN_HYBRID:
        result = agent_query(question, decision.intents, verbose=verbose)
    else:
        result = _run_vector_flow(question, verbose)

    result["intent"] = intent_result
    result["plan"] = decision.plan
    return result


def query_single(question: str, verbose: bool = True) -> dict:
    """方案A：单模型意图判断 + 工具调用（无小模型预分类）。

    大模型直接拿到工具集自主判断意图、调用工具并生成回答。
    返回: {"answer", "sources", "used_tools", "intents", "plan", "iterations"}
    """
    result = agent_query(question, [], verbose=verbose, with_guidance=False)
    # 记录方案标识
    result["plan"] = "single"
    return result


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
