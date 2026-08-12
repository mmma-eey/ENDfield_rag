"""意图识别模块 —— 基于 DeepSeek 小模型判断问题意图

输出两种意图（可同时）：
- INTENT_VECTOR   = "vector"   ：向量查询（语义/文本知识）
- INTENT_DATABASE = "database" ：数据库查询（结构化数值）
API 密钥从环境变量读取（rag.config 已加载 .env）。
"""
import json
import re
import time
from dataclasses import dataclass, field
from typing import List, Optional

from openai import OpenAI

from rag.config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, INTENT_MODEL
from rag.prompts import INTENT_SYSTEM_PROMPT

INTENT_VECTOR = "vector"        # 向量查询
INTENT_DATABASE = "database"    # 数据库查询
VALID_INTENTS = {INTENT_VECTOR, INTENT_DATABASE}

_client: Optional[OpenAI] = None


def _get_client() -> OpenAI:
    """从环境变量读取 DeepSeek API 密钥创建客户端（懒加载单例）"""
    global _client
    if _client is None:
        _client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
    return _client


@dataclass
class IntentResult:
    """意图判断结果"""
    intents: List[str] = field(default_factory=lambda: [INTENT_VECTOR])
    confidence: float = 1.0
    reason: str = ""
    raw: str = ""

    @property
    def is_hybrid(self) -> bool:
        """是否同时命中两种意图（混合路由）"""
        return len(self.intents) >= 2

    @property
    def primary(self) -> str:
        return self.intents[0] if self.intents else INTENT_VECTOR

    def has(self, intent: str) -> bool:
        return intent in self.intents


def parse_intent_response(content: str) -> Optional[List[str]]:
    """解析模型返回的意图 JSON，返回合法意图列表；解析失败返回 None。

    兼容：纯 JSON / ```json 代码围栏 / 前后附带说明文本。
    """
    if not content:
        return None
    text = content.strip()
    # 去除 markdown 代码围栏
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE).strip()
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    intents = data.get("intents")
    if not isinstance(intents, list) or not intents:
        return None
    cleaned = [i for i in intents if isinstance(i, str) and i in VALID_INTENTS]
    cleaned = list(dict.fromkeys(cleaned))  # 去重保序
    return cleaned or None


def classify_intent(question: str, max_retries: int = 2,
                    client: Optional[OpenAI] = None) -> IntentResult:
    """基于 DeepSeek 判断问题意图。

    - 模型返回 "vector" / "database" 之一或同时返回两者
    - 解析失败或 API 异常时最多重试 max_retries 次，仍失败则回退为默认向量查询
    """
    c = client or _get_client()
    messages = [
        {"role": "system", "content": INTENT_SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]
    last_raw = ""
    for attempt in range(max_retries + 1):
        try:
            resp = c.chat.completions.create(
                model=INTENT_MODEL,
                messages=messages,
                temperature=0.0,
                max_tokens=100,
            )
            content = resp.choices[0].message.content or ""
            last_raw = content
            intents = parse_intent_response(content)
            if intents:
                return IntentResult(intents=intents, raw=content)
        except Exception:
            pass
        if attempt < max_retries:
            time.sleep(0.5)
    return IntentResult(
        intents=[INTENT_VECTOR],
        confidence=0.0,
        reason="意图解析失败，回退为默认向量查询",
        raw=last_raw,
    )
