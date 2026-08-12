"""LangChain 工具封装 —— 向量查询 / 数据库查询（统一调用参数与返回格式）

- vector_search    ：语义向量检索知识库，返回带来源标签的文本切片
- database_query   ：结构化数据库查询，返回实体数值文本
两个工具均为 LangChain StructuredTool（@tool + pydantic args_schema），
可通过 to_openai_tool() 转换为 OpenAI Function Calling 格式。
"""
from typing import List

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from db.database import SessionLocal
from rag.bm25_index import BM25Index, clean_text
from rag.config import TOP_K_RERANK, TOP_K_RETRIEVAL
from rag.db_query import query_database
from rag.reranker import rerank
from rag.retriever import FUSION_RRF, hybrid_search

# 混合检索融合方式开关（评测时切换 rrf / minmax，默认 RRF）
FUSION_MODE = FUSION_RRF


class ToolRuntime:
    """工具执行期上下文 —— 跨工具记录检索来源与调用链。

    工具调用是黑盒（返回字符串），检索来源等信息经 runtime 透出，
    供 pipeline 构建引用来源与评测。每次问答前应调用 reset_runtime()。
    """

    def __init__(self) -> None:
        self.sources: List[dict] = []
        self.used_tools: List[str] = []
        self.vector_contexts: List[str] = []
        self.db_texts: List[str] = []


# 线程局部存储：并发评测时每个线程独立 runtime，避免相互覆盖
import threading
_local = threading.local()


def _get_runtime_obj() -> ToolRuntime:
    if not hasattr(_local, "runtime"):
        _local.runtime = ToolRuntime()
    return _local.runtime


def reset_runtime() -> None:
    """重置工具执行期上下文（每次问答开始前调用）"""
    _local.runtime = ToolRuntime()


def get_runtime() -> ToolRuntime:
    return _get_runtime_obj()


# ---- 工具参数 Schema ----
class VectorSearchArgs(BaseModel):
    question: str = Field(description="用户问题或需要检索的查询语句")
    top_k: int = Field(default=5, description="返回的切片数量（默认 5）")


class DatabaseQueryArgs(BaseModel):
    question: str = Field(description="需要查询数据库的问题，可含实体名与属性/等级需求")


# ---- 工具实现 ----
@tool(args_schema=VectorSearchArgs)
def vector_search(question: str, top_k: int = 5) -> str:
    """在《明日方舟：终末地》知识库中进行语义向量检索，返回与问题相关的文本资料（技能效果、天赋、档案、背景、机制说明等）。当问题需要文本知识时应优先使用本工具。"""
    session = SessionLocal()
    try:
        bm25 = BM25Index.load()
        if bm25 is None:
            return "向量知识库索引未构建，无法检索。"

        candidates = hybrid_search(session, bm25, question,
                                   top_k=TOP_K_RETRIEVAL, fusion=FUSION_MODE)
        documents = [c["content"] for c in candidates]
        reranked = rerank(question, documents, top_k=top_k)

        lines: List[str] = []
        sources: List[dict] = []
        for i, r in enumerate(reranked):
            orig = candidates[r["index"]]
            text = clean_text(r["document"])
            src_name = orig.get("source_name", "未知")
            src_type = orig.get("source_type", "unknown")
            chunk_type = orig.get("chunk_type", "")
            lines.append(f"[来源{i+1}][{src_name}][{chunk_type}] {text}")
            sources.append({
                "source_name": src_name,
                "source_type": src_type,
                "chunk_type": chunk_type,
                "content": text[:200],
                "rerank_score": r["score"],
            })

        runtime = get_runtime()
        runtime.sources.extend(sources)
        runtime.vector_contexts.extend(lines)
        runtime.used_tools.append("vector_search")

        return "\n".join(lines) if lines else "向量检索未找到相关文本资料。"
    finally:
        session.close()


@tool(args_schema=DatabaseQueryArgs)
def database_query(question: str) -> str:
    """查询《明日方舟：终末地》结构化数据库，返回干员/武器/敌人/装备的精确数值（等级属性、技能、掉落、获取方式等）。当问题涉及具体数值时应使用本工具。"""
    result = query_database(question)
    runtime = get_runtime()
    runtime.db_texts.append(result)
    runtime.used_tools.append("database_query")
    return result


# 工具注册表：小模型意图 → 大模型工具调用的唯一入口
TOOLS: dict = {"vector_search": vector_search, "database_query": database_query}


def to_openai_tool(ltool) -> dict:
    """LangChain StructuredTool → OpenAI Function Calling 格式"""
    schema = ltool.args_schema.model_json_schema() if ltool.args_schema \
        else {"type": "object", "properties": {}}
    return {
        "type": "function",
        "function": {
            "name": ltool.name,
            "description": ltool.description,
            "parameters": schema,
        },
    }
