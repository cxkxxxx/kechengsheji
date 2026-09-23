import json
import httpx
from app.core.config import LLM_API_URL, LLM_API_KEY, LLM_MODEL, LLM_VISION_MODEL


def call_llm(messages: list, tools: list = None) -> dict:
    # 调用大模型 API（非流式）
    # messages：对话历史
    # tools：可用工具列表（Function Calling 格式）
    # 返回：{"content": "回复文本", "tool_calls": [...]}
    model = LLM_VISION_MODEL if _has_image(messages) else LLM_MODEL
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 600,
    }
    if tools:
        payload["tools"] = tools

    with httpx.Client(timeout=45) as client:
        resp = client.post(
            LLM_API_URL, json=payload,
            headers={"Authorization": f"Bearer {LLM_API_KEY}", "Content-Type": "application/json"},
        )
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


def stream_llm(messages: list, tools: list = None):
    # 流式调用大模型，逐条 yield 分析后的分片
    # 每条 yields: {"delta": {...}, "finish_reason": str|None}
    # delta 可能是 {"content": "..."}，也可能是 {"tool_calls": [...]}
    model = LLM_VISION_MODEL if _has_image(messages) else LLM_MODEL
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 600,
        "stream": True,
    }
    if tools:
        payload["tools"] = tools

    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=60) as client:
        with client.stream("POST", LLM_API_URL, json=payload, headers=headers) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                line = (line or "").strip()
                if not line.startswith("data:"):
                    continue
                data = line[len("data:"):].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue
                choice = chunk.get("choices", [{}])[0]
                yield {
                    "delta": choice.get("delta", {}) or {},
                    "finish_reason": choice.get("finish_reason"),
                }


def _has_image(messages: list) -> bool:
    # 判断当前消息序列是否含图片（多模态内容），若有则切换视觉模型
    for m in messages:
        c = m.get("content")
        if isinstance(c, list):
            for part in c:
                if isinstance(part, dict) and part.get("type") == "image_url":
                    return True
    return False