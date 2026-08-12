"""Pipeline 编排单元测试 —— 意图→路由→处理流程分发（mock 小模型与各流程）"""
from unittest.mock import patch

from rag.intent import (INTENT_DATABASE, INTENT_VECTOR, IntentResult)
from rag.pipeline import query


def _intent(intents):
    return IntentResult(intents=list(intents))


class TestPipelineRouting:
    def test_vector_plan(self):
        with patch("rag.pipeline.classify_intent", return_value=_intent([INTENT_VECTOR])) as m_cls, \
             patch("rag.pipeline._run_vector_flow", return_value={"answer": "A", "sources": []}) as m_vf, \
             patch("rag.pipeline._run_database_flow") as m_df, \
             patch("rag.pipeline.agent_query") as m_agent:
            result = query("卡缪的背景故事是什么", verbose=False)
        assert result["answer"] == "A"
        assert result["plan"] == "vector"
        assert result["intent"].intents == [INTENT_VECTOR]
        m_cls.assert_called_once_with("卡缪的背景故事是什么")
        m_vf.assert_called_once()
        m_df.assert_not_called()
        m_agent.assert_not_called()

    def test_database_plan(self):
        with patch("rag.pipeline.classify_intent", return_value=_intent([INTENT_DATABASE])), \
             patch("rag.pipeline._run_vector_flow") as m_vf, \
             patch("rag.pipeline._run_database_flow", return_value={"answer": "B", "sources": [{"source_name": "卡缪"}]}) as m_df, \
             patch("rag.pipeline.agent_query") as m_agent:
            result = query("卡缪90级攻击力是多少", verbose=False)
        assert result["plan"] == "database"
        assert result["answer"] == "B"
        m_df.assert_called_once()
        m_vf.assert_not_called()
        m_agent.assert_not_called()

    def test_hybrid_plan_uses_agent(self):
        with patch("rag.pipeline.classify_intent",
                   return_value=_intent([INTENT_VECTOR, INTENT_DATABASE])), \
             patch("rag.pipeline._run_vector_flow") as m_vf, \
             patch("rag.pipeline._run_database_flow") as m_df, \
             patch("rag.pipeline.agent_query",
                   return_value={"answer": "C", "sources": [], "used_tools": ["vector_search", "database_query"]}) as m_agent:
            result = query("对比武器并给出数值", verbose=False)
        assert result["plan"] == "hybrid"
        assert result["answer"] == "C"
        m_agent.assert_called_once()
        # 意图原样传给大模型工具调用编排
        args, kwargs = m_agent.call_args
        assert args[1] == [INTENT_VECTOR, INTENT_DATABASE]
        m_vf.assert_not_called()
        m_df.assert_not_called()

    def test_empty_intent_falls_back_to_vector(self):
        # 小模型识别失败 → 默认向量路由（安全路径）
        with patch("rag.pipeline.classify_intent", return_value=_intent([])), \
             patch("rag.pipeline._run_vector_flow", return_value={"answer": "D", "sources": []}) as m_vf:
            result = query("未知类型问题", verbose=False)
        assert result["plan"] == "vector"
        assert result["intent"].intents == []
        m_vf.assert_called_once()
