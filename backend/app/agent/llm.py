import httpx
from app.core.config import LLM_API_URL, LLM_API_KEY, LLM_MODEL


def call_llm(messages: list, tools: list = None) -> dict:
    # 调用大模型 API
    # messages：对话历史
    # tools：可用工具列表（Function Calling 格式）
    # 返回：{"content": "回复文本", "tool_calls": [...]}
    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": LLM_MODEL,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 2000,
    }
    if tools:
        payload["tools"] = tools

    with httpx.Client(timeout=30) as client:
        resp = client.post(LLM_API_URL, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    choice = data["choices"][0]["message"]
    return {
        "content": choice.get("content", "") or "",
        "tool_calls": choice.get("tool_calls") or [],
    }


def call_llm_simple(prompt: str, system: str = "") -> str:
    # 简单调用（不用工具，直接问答）
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    result = call_llm(messages)
    return result["content"]
