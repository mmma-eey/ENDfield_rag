"""大模型 Tool Calling 编排 —— 小模型意图指导大模型调用工具

流程：小模型给出意图（vector/database/混合）→ 拼接意图引导提示词 →
     大模型（DeepSeek）自主决定调用 vector_search / database_query →
     执行工具并回填结果 → 迭代至大模型给出最终回答。
"""
import json
import time
from typing import Dict, List, Optional

from openai import OpenAI

from rag.config import (DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, LLM_MODEL,
                        MAX_AGENT_ITERATIONS)
from rag.prompts import AGENT_SYSTEM_PROMPT, build_intent_guidance
from rag.tools import TOOLS, get_runtime, reset_runtime, to_openai_tool

_client: Optional[OpenAI] = None


def _get_client() -> OpenAI:
    """从环境变量读取 DeepSeek API 密钥创建客户端（懒加载单例）"""
    global _client
    if _client is None:
        _client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
    return _client


def _execute_tool_call(tool_call, tools: Dict) -> dict:
    """解析并执行一次工具调用，返回 OpenAI tool 角色消息（含错误兜底）"""
    name = getattr(getattr(tool_call, "function", None), "name", "")
    try:
        args = json.loads(tool_call.function.arguments or "{}")
        if not isinstance(args, dict):
            args = {}
    except json.JSONDecodeError:
        return {"role": "tool", "tool_call_id": tool_call.id,
                "content": f"工具 {name} 参数解析失败：无效的 JSON"}
    tool = tools.get(name)
    if tool is None:
        return {"role": "tool", "tool_call_id": tool_call.id,
                "content": f"未找到工具：{name}"}
    try:
        result = tool.invoke(args)
        return {"role": "tool", "tool_call_id": tool_call.id, "content": str(result)}
    except Exception as e:  # 工具执行异常反馈给大模型继续处理
        return {"role": "tool", "tool_call_id": tool_call.id,
                "content": f"工具 {name} 执行出错：{e}"}


def _assistant_message_to_dict(msg) -> dict:
    """OpenAI 消息对象 → dict（保留 tool_calls 供回填）"""
    d = {"role": "assistant", "content": msg.content}
    tool_calls = getattr(msg, "tool_calls", None) or []
    if tool_calls:
        d["tool_calls"] = [
            {"id": tc.id, "type": "function",
             "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
            for tc in tool_calls
        ]
    return d


def agent_query(question: str, intents: List[str], verbose: bool = False,
                max_iterations: Optional[int] = None,
                client: Optional[OpenAI] = None,
                tools: Optional[Dict] = None,
                with_guidance: bool = True) -> dict:
    """大模型 Tool Calling —— 单模型自主意图判断 + 工具调用。

    - with_guidance=True （方案B）：小模型先判断意图，引导大模型调用工具
    - with_guidance=False（方案A）：不预分类，大模型单模型自主判断意图并调用工具

    返回: {"answer", "sources", "used_tools", "intents", "plan", "iterations"}
    """
    reset_runtime()
    max_iterations = max_iterations or MAX_AGENT_ITERATIONS
    tools = tools or TOOLS
    c = client or _get_client()

    # 小模型意图 → 大模型工具调用引导（方案A 不附加，由大模型自主判断）
    if with_guidance:
        guidance = build_intent_guidance(intents)
        system = AGENT_SYSTEM_PROMPT + "\n\n## 本次意图分析\n" + guidance
    else:
        system = AGENT_SYSTEM_PROMPT
    messages: List[dict] = [
        {"role": "system", "content": system},
        {"role": "user", "content": question},
    ]
    openai_tools = [to_openai_tool(t) for t in tools.values()]

    if verbose:
        print(f"[Agent] 意图引导={'开启' if with_guidance else '关闭(单模型自主)'} | "
              f"可用工具={list(tools.keys())} | 最大迭代={max_iterations}")

    final_answer = ""
    used_iterations = 0
    executed_tools: List[str] = []
    for iteration in range(1, max_iterations + 1):
        resp = c.chat.completions.create(
            model=LLM_MODEL,
            messages=messages,
            tools=openai_tools,
            temperature=0.3,
            max_tokens=1024,
        )
        msg = resp.choices[0].message

        tool_calls = getattr(msg, "tool_calls", None) or []
        if tool_calls:
            messages.append(_assistant_message_to_dict(msg))
            for tc in tool_calls:
                messages.append(_execute_tool_call(tc, tools))
                executed_tools.append(getattr(getattr(tc, "function", None), "name", ""))
            if verbose:
                names = [tc.function.name for tc in tool_calls]
                print(f"[Agent] 第{iteration}轮调用工具: {names}")
            continue

        content = (msg.content or "").strip()
        if content:
            final_answer = content
            used_iterations = iteration
            break
        # DeepSeek 偶发返回空 content：重试
        if iteration < max_iterations:
            time.sleep(1.0)

    if not final_answer:
        final_answer = "（工具调用结束，未能生成有效回答）"

    runtime = get_runtime()
    return {
        "answer": final_answer,
        "sources": runtime.sources,
        "used_tools": executed_tools,
        "intents": list(intents),
        "plan": "hybrid",
        "iterations": used_iterations,
    }
