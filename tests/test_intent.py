"""意图识别模块单元测试 —— 解析逻辑与 DeepSeek 调用（mock，不联网）"""
import pytest

from rag.intent import (INTENT_DATABASE, INTENT_VECTOR, IntentResult,
                        classify_intent, parse_intent_response)
from rag.config import INTENT_MODEL


# ---------- Fake OpenAI 客户端 ----------
class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content):
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


class _FakeCompletions:
    """依次弹出预设响应；Exception 会被直接抛出模拟 API 异常"""
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0
        self.kwargs_log = []

    def create(self, **kwargs):
        self.calls += 1
        self.kwargs_log.append(kwargs)
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return _FakeResponse(r)


class _FakeChat:
    def __init__(self, responses):
        self.completions = _FakeCompletions(responses)


class _FakeClient:
    def __init__(self, responses):
        self.chat = _FakeChat(responses)


# ---------- parse_intent_response ----------
class TestParseIntentResponse:
    def test_single_vector(self):
        assert parse_intent_response('{"intents": ["vector"]}') == [INTENT_VECTOR]

    def test_single_database(self):
        assert parse_intent_response('{"intents": ["database"]}') == [INTENT_DATABASE]

    def test_hybrid_both(self):
        assert parse_intent_response('{"intents": ["vector", "database"]}') == \
            [INTENT_VECTOR, INTENT_DATABASE]

    def test_code_fenced_json(self):
        assert parse_intent_response('```json\n{"intents":["vector"]}\n```') == [INTENT_VECTOR]

    def test_surrounding_text(self):
        assert parse_intent_response('判断结果如下：{"intents":["database"]}') == [INTENT_DATABASE]

    def test_duplicates_deduped(self):
        assert parse_intent_response('{"intents":["vector","vector","database"]}') == \
            [INTENT_VECTOR, INTENT_DATABASE]

    def test_empty_content(self):
        assert parse_intent_response("") is None
        assert parse_intent_response(None) is None

    def test_invalid_json(self):
        assert parse_intent_response("这不是 JSON") is None
        assert parse_intent_response('{"intents": [}') is None

    def test_missing_intents_key(self):
        assert parse_intent_response('{"foo": "bar"}') is None

    def test_empty_intents_list(self):
        assert parse_intent_response('{"intents": []}') is None

    def test_unknown_intent_name(self):
        assert parse_intent_response('{"intents": ["sql"]}') is None

    def test_partial_valid_intents(self):
        assert parse_intent_response('{"intents": ["vector", "mysql"]}') == [INTENT_VECTOR]


# ---------- classify_intent ----------
class TestClassifyIntent:
    def test_classify_vector(self):
        client = _FakeClient(['{"intents": ["vector"]}'])
        result = classify_intent("卡缪的背景故事是什么", client=client)
        assert isinstance(result, IntentResult)
        assert result.intents == [INTENT_VECTOR]
        assert result.confidence == 1.0

    def test_classify_database(self):
        client = _FakeClient(['{"intents": ["database"]}'])
        result = classify_intent("卡缪90级攻击力是多少", client=client)
        assert result.intents == [INTENT_DATABASE]

    def test_classify_hybrid(self):
        client = _FakeClient(['{"intents": ["vector", "database"]}'])
        result = classify_intent("镀红祝福和灯火使命哪个更适合卡缪", client=client)
        assert result.intents == [INTENT_VECTOR, INTENT_DATABASE]
        assert result.is_hybrid is True

    def test_retry_after_empty_response(self):
        client = _FakeClient(["", '{"intents": ["database"]}'])
        result = classify_intent("问题", client=client)
        assert result.intents == [INTENT_DATABASE]
        assert client.chat.completions.calls == 2

    def test_retry_after_invalid_response(self):
        client = _FakeClient(["无法解析", '{"intents": ["vector"]}'])
        result = classify_intent("问题", client=client)
        assert result.intents == [INTENT_VECTOR]
        assert client.chat.completions.calls == 2

    def test_fallback_on_api_exception(self):
        client = _FakeClient([Exception("connection refused")])
        result = classify_intent("问题", client=client)
        assert result.intents == [INTENT_VECTOR]
        assert result.confidence == 0.0
        assert "回退" in result.reason

    def test_fallback_after_all_retries_fail(self):
        client = _FakeClient(["坏响应", "坏响应", "坏响应"])
        result = classify_intent("问题", client=client)
        assert result.intents == [INTENT_VECTOR]
        assert client.chat.completions.calls == 3

    def test_request_uses_intent_model_and_question(self):
        client = _FakeClient(['{"intents": ["vector"]}'])
        classify_intent("卡缪是什么职业", client=client)
        kwargs = client.chat.completions.kwargs_log[0]
        assert kwargs["model"] == INTENT_MODEL
        assert kwargs["messages"][-1]["content"] == "卡缪是什么职业"

    def test_intent_result_helpers(self):
        r = IntentResult(intents=[INTENT_DATABASE])
        assert r.primary == INTENT_DATABASE
        assert r.has(INTENT_DATABASE)
        assert r.is_hybrid is False
        assert IntentResult(intents=[INTENT_VECTOR, INTENT_DATABASE]).is_hybrid is True
