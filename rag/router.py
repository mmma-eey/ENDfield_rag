"""意图路由 —— 根据小模型意图将请求分发到相应处理流程

支持三种路由计划：
- PLAN_VECTOR   ：单一意图，仅向量查询
- PLAN_DATABASE ：单一意图，仅数据库查询
- PLAN_HYBRID   ：混合意图，向量 + 数据库（走大模型 Tool Calling）
"""
from dataclasses import dataclass
from typing import Callable, Dict, List

from rag.intent import INTENT_DATABASE, INTENT_VECTOR

PLAN_VECTOR = "vector"
PLAN_DATABASE = "database"
PLAN_HYBRID = "hybrid"

_PLAN_LABELS = {
    PLAN_VECTOR: "向量查询",
    PLAN_DATABASE: "数据库查询",
    PLAN_HYBRID: "混合查询（向量 + 数据库）",
}


@dataclass
class RouteDecision:
    """路由决策结果"""
    plan: str
    intents: List[str]

    @property
    def is_single(self) -> bool:
        return self.plan != PLAN_HYBRID

    def describe(self) -> str:
        return f"{_PLAN_LABELS.get(self.plan, self.plan)}（意图: {self.intents}）"


def decide_route(intents: List[str]) -> RouteDecision:
    """意图列表 → 路由决策。

    - 空 / 非法意图 → 回退为向量路由（默认安全路径）
    - 单一意图 → 对应单一路由
    - 两种意图同时命中 → 混合路由
    """
    valid = [i for i in intents if i in (INTENT_VECTOR, INTENT_DATABASE)]
    valid = list(dict.fromkeys(valid))  # 去重保序
    if not valid:
        return RouteDecision(plan=PLAN_VECTOR, intents=[INTENT_VECTOR])
    if len(valid) >= 2:
        return RouteDecision(plan=PLAN_HYBRID, intents=valid)
    return RouteDecision(plan=valid[0], intents=valid)


class Router:
    """可注册处理器的意图路由器 —— 单一/混合路由分发。"""

    def __init__(self) -> None:
        self._handlers: Dict[str, Callable] = {}

    def register(self, plan: str, handler: Callable) -> None:
        """注册某路由计划的处理函数：handler(question, **kwargs) -> dict"""
        self._handlers[plan] = handler

    def route(self, intents: List[str]) -> RouteDecision:
        return decide_route(intents)

    def dispatch(self, intents: List[str], question: str, **kwargs) -> dict:
        """按意图分发请求到对应处理流程，返回 {"plan", "intents", "result"}"""
        decision = decide_route(intents)
        handler = self._handlers.get(decision.plan)
        if handler is None:
            raise KeyError(f"未注册路由处理器: {decision.plan}")
        result = handler(question, **kwargs)
        return {"plan": decision.plan, "intents": decision.intents, "result": result}
