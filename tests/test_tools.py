"""LangChain 工具封装单元测试 —— 工具接口/返回格式/执行期上下文（mock，不联网不依赖 DB）"""
import pytest
from unittest.mock import patch

from rag.tools import (TOOLS, get_runtime, reset_runtime, to_openai_tool,
                       vector_search, database_query)


@pytest.fixture(autouse=True)
def _reset_runtime():
    reset_runtime()
    yield
    reset_runtime()


def _candidates():
    return [
        {"content": "卡缪的战技驱火焚影：对目标造成灼热伤害，并使灼热附着。",
         "source_name": "卡缪", "source_type": "operator",
         "chunk_type": "operator_skills",
         "bm25_score": 1.0, "vector_score": 0.9, "combined_score": 0.03},
        {"content": "镀红祝福：主属性敏捷，适合灼热系干员。",
         "source_name": "镀红祝福", "source_type": "weapon",
         "chunk_type": "weapon_skill",
         "bm25_score": 0.8, "vector_score": 0.7, "combined_score": 0.02},
    ]


class TestToolSchema:
    def test_tools_registry(self):
        assert set(TOOLS.keys()) == {"vector_search", "database_query"}

    def test_to_openai_tool_vector_search(self):
        schema = to_openai_tool(vector_search)
        assert schema["type"] == "function"
        fn = schema["function"]
        assert fn["name"] == "vector_search"
        assert fn["description"]
        props = fn["parameters"]["properties"]
        assert "question" in props and "top_k" in props
        assert fn["parameters"]["required"] == ["question"]

    def test_to_openai_tool_database_query(self):
        schema = to_openai_tool(database_query)
        fn = schema["function"]
        assert fn["name"] == "database_query"
        assert list(fn["parameters"]["properties"].keys()) == ["question"]
        assert fn["parameters"]["required"] == ["question"]


class TestVectorSearchTool:
    @pytest.fixture
    def patched(self):
        with patch("rag.tools.SessionLocal") as m_session, \
             patch("rag.tools.BM25Index.load", return_value=object()), \
             patch("rag.tools.hybrid_search", return_value=_candidates()), \
             patch("rag.tools.rerank", return_value=[
                 {"index": 0, "score": 0.95, "document": _candidates()[0]["content"]},
                 {"index": 1, "score": 0.80, "document": _candidates()[1]["content"]},
             ]):
            m_session.return_value.close = lambda: None
            yield

    def test_invoke_returns_formatted_text(self, patched):
        out = vector_search.invoke({"question": "卡缪的战技是什么", "top_k": 2})
        assert isinstance(out, str)
        assert "卡缪" in out and "operator_skills" in out
        assert out.count("[来源") == 2

    def test_runtime_records_sources_and_contexts(self, patched):
        vector_search.invoke({"question": "卡缪的战技是什么", "top_k": 2})
        rt = get_runtime()
        assert len(rt.sources) == 2
        assert rt.sources[0]["source_name"] == "卡缪"
        assert rt.sources[0]["source_type"] == "operator"
        assert rt.used_tools == ["vector_search"]
        assert len(rt.vector_contexts) == 2

    def test_clean_text_removes_wiki_tags(self, patched):
        out = vector_search.invoke({"question": "x", "top_k": 1})
        assert "<" not in out and "{" not in out


class TestDatabaseQueryTool:
    def test_invoke_returns_db_text(self):
        with patch("rag.tools.query_database", return_value="[卡缪][basic]卡缪，6星先锋；攻击力成长……") as m_q:
            out = database_query.invoke({"question": "卡缪90级攻击力"})
            m_q.assert_called_once_with("卡缪90级攻击力")
            assert out.startswith("[卡缪]")

    def test_runtime_records_used_tool(self):
        with patch("rag.tools.query_database", return_value="数据"):
            database_query.invoke({"question": "纾难识别牌获取方式"})
        rt = get_runtime()
        assert rt.used_tools == ["database_query"]
        assert rt.db_texts == ["数据"]

    def test_query_not_found_message(self):
        with patch("rag.tools.query_database", return_value="数据库查询未找到相关实体数据。"):
            out = database_query.invoke({"question": "无关问题"})
        assert "未找到" in out


class TestResetRuntime:
    def test_reset_clears_state(self):
        with patch("rag.tools.hybrid_search", return_value=_candidates()), \
             patch("rag.tools.rerank", return_value=[
                 {"index": 0, "score": 0.95, "document": _candidates()[0]["content"]}]):
            vector_search.invoke({"question": "q", "top_k": 1})
        assert get_runtime().sources
        reset_runtime()
        assert get_runtime().sources == []
        assert get_runtime().used_tools == []
