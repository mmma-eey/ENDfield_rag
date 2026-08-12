"""大模型 Tool Calling 编排单元测试 —— 工具调用解析/执行/结果回填/错误兜底（mock，不联网）"""
import json

import pytest

from rag.agent import (_assistant_message_to_dict, _execute_tool_call,
                       agent_query)
from rag.intent import INTENT_DATABASE, INTENT_VECTOR


# ---------- Fake OpenAI 客户端（支持 tool_calls） ----------
class _Fn:
    def __init__(self, name, args):
        self.name = name
        self.arguments = json.dumps(args, ensure_ascii=False)


class _ToolCall:
    def __init__(self, tid, name, args):
        self.id = tid
        self.function = _Fn(name, args)


class _Msg:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class _Choice:
    def __init__(self, msg):
        self.message = msg


class _Resp:
    def __init__(self, msg):
        self.choices = [_Choice(msg)]


class _Completions:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0
        self.kwargs_log = []

    def create(self, **kwargs):
        self.calls += 1
        self.kwargs_log.append(kwargs)
        return self.responses.pop(0)


class _Chat:
    def __init__(self, responses):
        self.completions = _Completions(responses)


class _FakeClient:
    def __init__(self, responses):
        self.chat = _Chat(responses)


def _tc(tid, name, args):
    return _ToolCall(tid, name, args)


def _tool_call_response(*tool_calls):
    return _Resp(_Msg(content=None, tool_calls=list(tool_calls)))


def _content_response(content):
    return _Resp(_Msg(content=content))


class FakeTool:
    """可记录调用参数的伪工具"""
    def __init__(self, name, result="工具结果", raise_on_invoke=False):
        self.name = name
        self.description = f"{name} 的说明"
        self.args_schema = None
        self.result = result
        self.raise_on_invoke = raise_on_invoke
        self.invoked = []

    def invoke(self, args):
        if self.raise_on_invoke:
            raise RuntimeError("模拟执行失败")
        self.invoked.append(args)
        return self.result


class TestExecuteToolCall:
    def test_valid_call_invokes_tool(self):
        tool = FakeTool("vector_search", "检索结果")
        msg = _execute_tool_call(_tc("t1", "vector_search", {"question": "q", "top_k": 3}),
                                 {"vector_search": tool})
        assert msg["role"] == "tool"
        assert msg["tool_call_id"] == "t1"
        assert msg["content"] == "检索结果"
        assert tool.invoked == [{"question": "q", "top_k": 3}]

    def test_invalid_json_args(self):
        tc = _ToolCall("t2", "vector_search", None)
        tc.function.arguments = "not-a-json"
        msg = _execute_tool_call(tc, {})
        assert "解析失败" in msg["content"]
        assert "无效的 JSON" in msg["content"]

    def test_unknown_tool_name(self):
        msg = _execute_tool_call(_tc("t3", "no_such_tool", {}), {})
        assert "未找到工具" in msg["content"]

    def test_tool_execution_error(self):
        tool = FakeTool("database_query", raise_on_invoke=True)
        msg = _execute_tool_call(_tc("t4", "database_query", {"question": "q"}),
                                 {"database_query": tool})
        assert "执行出错" in msg["content"]
        assert "模拟执行失败" in msg["content"]


class TestAssistantToDict:
    def test_with_tool_calls(self):
        msg = _Msg(content=None, tool_calls=[_tc("c1", "vector_search", {"question": "q"})])
        d = _assistant_message_to_dict(msg)
        assert d["role"] == "assistant"
        assert d["tool_calls"][0]["function"]["name"] == "vector_search"
        assert d["tool_calls"][0]["id"] == "c1"

    def test_without_tool_calls(self):
        d = _assistant_message_to_dict(_Msg(content="hi"))
        assert d["content"] == "hi"
        assert "tool_calls" not in d


class TestAgentQuery:
    def test_tool_call_then_final_answer(self):
        tool = FakeTool("vector_search", "检索资料")
        client = _FakeClient([
            _tool_call_response(_tc("c1", "vector_search", {"question": "卡缪的战技"})),
            _content_response("卡缪的战技是驱火焚影，造成灼热伤害。"),
        ])
        result = agent_query("卡缪的战技是什么", [INTENT_VECTOR],
                             client=client, tools={"vector_search": tool})
        assert result["answer"] == "卡缪的战技是驱火焚影，造成灼热伤害。"
        assert tool.invoked == [{"question": "卡缪的战技"}]
        assert result["used_tools"] == ["vector_search"]
        assert result["iterations"] == 2
        assert result["intents"] == [INTENT_VECTOR]

    def test_hybrid_two_tool_calls_in_one_turn(self):
        vt = FakeTool("vector_search", "文本资料")
        dt = FakeTool("database_query", "数值资料")
        client = _FakeClient([
            _tool_call_response(
                _tc("c1", "vector_search", {"question": "镀红祝福"}),
                _tc("c2", "database_query", {"question": "卡缪属性"}),
            ),
            _content_response("综合结果。"),
        ])
        result = agent_query("对比", [INTENT_VECTOR, INTENT_DATABASE],
                             client=client, tools={"vector_search": vt, "database_query": dt})
        assert result["answer"] == "综合结果。"
        assert vt.invoked == [{"question": "镀红祝福"}]
        assert dt.invoked == [{"question": "卡缪属性"}]
        assert result["used_tools"] == ["vector_search", "database_query"]

    def test_tool_results_fed_back_to_llm(self):
        tool = FakeTool("vector_search", "工具返回内容")
        client = _FakeClient([
            _tool_call_response(_tc("c1", "vector_search", {"question": "q"})),
            _content_response("答"),
        ])
        agent_query("q", [INTENT_VECTOR], client=client, tools={"vector_search": tool})
        second_call_msgs = client.chat.completions.kwargs_log[1]["messages"]
        tool_msgs = [m for m in second_call_msgs if m["role"] == "tool"]
        assert len(tool_msgs) == 1
        assert tool_msgs[0]["content"] == "工具返回内容"
        assert tool_msgs[0]["tool_call_id"] == "c1"
        # 首轮传入 OpenAI Function 格式的工具定义
        assert client.chat.completions.kwargs_log[0]["tools"][0]["type"] == "function"

    def test_system_prompt_contains_intent_guidance(self):
        client = _FakeClient([_content_response("答")])
        agent_query("q", [INTENT_DATABASE], client=client, tools={"database_query": FakeTool("database_query")})
        system_content = client.chat.completions.kwargs_log[0]["messages"][0]["content"]
        assert "本次意图分析" in system_content
        assert "database_query" in system_content

    def test_empty_content_retry(self):
        client = _FakeClient([
            _content_response(""),
            _content_response("重试后的回答"),
        ])
        result = agent_query("q", [INTENT_VECTOR], client=client, tools={})
        assert result["answer"] == "重试后的回答"
        assert client.chat.completions.calls == 2

    def test_max_iterations_exhausted(self):
        client = _FakeClient([
            _content_response(""),
            _content_response(""),
            _content_response(""),
        ])
        result = agent_query("q", [INTENT_VECTOR], client=client, tools={},
                             max_iterations=3)
        assert "未能生成" in result["answer"]
        assert client.chat.completions.calls == 3

    def test_tool_error_fed_back_then_answer(self):
        tool = FakeTool("database_query", raise_on_invoke=True)
        client = _FakeClient([
            _tool_call_response(_tc("c1", "database_query", {"question": "q"})),
            _content_response("已重试完成"),
        ])
        result = agent_query("q", [INTENT_DATABASE], client=client,
                             tools={"database_query": tool})
        assert result["answer"] == "已重试完成"
        tool_msgs = [m for m in client.chat.completions.kwargs_log[1]["messages"]
                     if m["role"] == "tool"]
        assert "执行出错" in tool_msgs[0]["content"]
