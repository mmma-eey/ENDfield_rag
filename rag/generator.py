"""DeepSeek 生成器 —— 基于检索到的上下文回答问题"""
from openai import OpenAI

from rag.config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, LLM_MODEL

client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)

from rag.prompts import GENERATION_SYSTEM_PROMPT


def generate(question: str, contexts: list[str]) -> str:
    """基于上下文列表生成回答。"""
    context_text = "\n\n---\n\n".join(
        f"[来源 {i+1}]\n{ctx}" for i, ctx in enumerate(contexts)
    )

    messages = [
        {"role": "system", "content": GENERATION_SYSTEM_PROMPT},
        {"role": "user", "content": f"参考资料：\n{context_text}\n\n用户问题：{question}"},
    ]

    resp = client.chat.completions.create(
        model=LLM_MODEL,
        messages=messages,
        temperature=0.3,
        max_tokens=1024,
    )

    return resp.choices[0].message.content


def chat_with_history(messages: list[dict], contexts: list[str]) -> str:
    """带对话历史的生成（Phase 4 多轮用）。"""
    context_text = "\n\n---\n\n".join(
        f"[来源 {i+1}]\n{ctx}" for i, ctx in enumerate(contexts)
    )

    system_msg = {
        "role": "system",
        "content": SYSTEM_PROMPT + f"\n\n当前参考资料：\n{context_text}"
    }

    resp = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[system_msg] + messages,
        temperature=0.3,
        max_tokens=1024,
    )

    return resp.choices[0].message.content
