"""意图路由单元测试 —— 单一/混合路由决策与分发"""
import pytest

from rag.intent import INTENT_DATABASE, INTENT_VECTOR
from rag.router import (PLAN_DATABASE, PLAN_HYBRID, PLAN_VECTOR, RouteDecision,
                        Router, decide_route)


class TestDecideRoute:
    def test_single_vector(self):
        d = decide_route([INTENT_VECTOR])
        assert d.plan == PLAN_VECTOR
        assert d.is_single

    def test_single_database(self):
        d = decide_route([INTENT_DATABASE])
        assert d.plan == PLAN_DATABASE
        assert d.is_single

    def test_hybrid_both(self):
        d = decide_route([INTENT_VECTOR, INTENT_DATABASE])
        assert d.plan == PLAN_HYBRID
        assert not d.is_single

    def test_hybrid_order_independent(self):
        d = decide_route([INTENT_DATABASE, INTENT_VECTOR])
        assert d.plan == PLAN_HYBRID

    def test_empty_intents_fallback_to_vector(self):
        d = decide_route([])
        assert d.plan == PLAN_VECTOR

    def test_invalid_intents_fallback_to_vector(self):
        d = decide_route(["sql", "nonsense"])
        assert d.plan == PLAN_VECTOR
        assert d.intents == [INTENT_VECTOR]

    def test_duplicates_deduped(self):
        d = decide_route([INTENT_VECTOR, INTENT_VECTOR, INTENT_DATABASE])
        assert d.plan == PLAN_HYBRID
        assert d.intents == [INTENT_VECTOR, INTENT_DATABASE]

    def test_describe(self):
        d = decide_route([INTENT_VECTOR, INTENT_DATABASE])
        assert "混合" in d.describe()
        assert decide_route([INTENT_DATABASE]).describe() != ""


class TestRouterDispatch:
    def _make_handlers(self):
        calls = {"vector": [], "database": [], "hybrid": []}

        def vh(question, **kw):
            calls["vector"].append(question)
            return {"flow": "vector"}

        def dh(question, **kw):
            calls["database"].append(question)
            return {"flow": "database"}

        def hh(question, **kw):
            calls["hybrid"].append(question)
            return {"flow": "hybrid"}
        return calls, vh, dh, hh

    def test_dispatch_vector_handler(self):
        calls, vh, dh, hh = self._make_handlers()
        r = Router()
        r.register(PLAN_VECTOR, vh)
        r.register(PLAN_DATABASE, dh)
        r.register(PLAN_HYBRID, hh)
        out = r.dispatch([INTENT_VECTOR], "问题A")
        assert out["plan"] == PLAN_VECTOR
        assert out["result"]["flow"] == "vector"
        assert calls["vector"] == ["问题A"]
        assert calls["hybrid"] == []

    def test_dispatch_database_handler(self):
        calls, vh, dh, hh = self._make_handlers()
        r = Router()
        r.register(PLAN_VECTOR, vh)
        r.register(PLAN_DATABASE, dh)
        r.register(PLAN_HYBRID, hh)
        r.dispatch([INTENT_DATABASE], "问题B")
        assert calls["database"] == ["问题B"]

    def test_dispatch_hybrid_handler(self):
        calls, vh, dh, hh = self._make_handlers()
        r = Router()
        r.register(PLAN_VECTOR, vh)
        r.register(PLAN_DATABASE, dh)
        r.register(PLAN_HYBRID, hh)
        out = r.dispatch([INTENT_VECTOR, INTENT_DATABASE], "问题C")
        assert out["plan"] == PLAN_HYBRID
        assert calls["hybrid"] == ["问题C"]
        assert calls["vector"] == [] and calls["database"] == []

    def test_dispatch_unregistered_plan_raises(self):
        r = Router()
        with pytest.raises(KeyError):
            r.dispatch([INTENT_VECTOR], "问题")

    def test_route_returns_decision(self):
        r = Router()
        d = r.route([INTENT_VECTOR])
        assert isinstance(d, RouteDecision)
        assert d.plan == PLAN_VECTOR
