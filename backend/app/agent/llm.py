import json
import logging

import httpx

from app.core.config import (LLM_API_URL, LLM_API_KEY, LLM_MODEL, LLM_VISION_MODEL, LLM_MAX_TOKENS)

log = logging.getLogger("llm")

# 视觉模型 glm-4v-flash 的 max_tokens 上限只有 1024，文本模型 glm-4-flash 实测到 8000 都收。
# 超过上限时智谱返回 400（错误码 1210），整条图片对话直接失败，所以在发出去之前夹住。
VISION_MAX_TOKENS = 1024


class LLMError(RuntimeError):
    """给用户的短消息；完整原因写日志，不往小程序里吐 URL 和堆栈。"""

    def __init__(self, brief: str, detail: str = ""):
        super().__init__(brief)
        self.brief = brief
        self.detail = detail or brief


def friendly_error(e: Exception) -> str:
    """把异常收敛成一句人话。额度、鉴权、限流、参数配错各自给对应提示。"""
    if isinstance(e, LLMError):
        return e.brief          # brief 本来就是给人看的，别用通用文案盖掉它
    if isinstance(e, httpx.TimeoutException):
        return "模型响应超时，请稍后再试"
    text = str(e)
    low = text.lower()
    # 状态码判断不看异常类型：_raise_for_status 造出来的是 RuntimeError，
    # 走 httpx 分支会全部漏掉，只能退成「服务暂时不可用」。
    if "余额" in text or "资源包" in text or "402" in text:
        return "模型服务额度不足，请联系管理员充值"
    if "401" in text or "unauthorized" in low:
        return "模型服务鉴权失败（API 密钥无效或过期），请联系管理员检查配置"
    if "429" in text or "too many" in low:
        return "模型调用过于频繁，稍等几秒再试"
    # 智谱 1210 = 请求参数非法，是我们的配置问题，说「稍后再试」会把真因藏起来
    if "参数非法" in text:
        return "模型请求参数配置有误，请联系管理员检查 .env"
    if isinstance(e, httpx.HTTPError) or "http " in low:
        return "模型服务暂时不可用，请稍后再试"
    return "模型服务返回异常，请稍后再试"


def _max_tokens_for(model: str) -> int:
    return min(LLM_MAX_TOKENS, VISION_MAX_TOKENS) if model == LLM_VISION_MODEL else LLM_MAX_TOKENS


def _raise_for_status(resp) -> None:
    # 不用 raise_for_status()：它只留下状态行，厂商 error.message 里的真实原因
    # （比如「max_tokens 参数非法」）会被丢掉，出问题时日志里查不到。
    if resp.is_success:
        return
    try:
        resp.read()          # 流式响应要先读体才有 .text；普通响应是幂等的
        detail = (resp.text or "")[:300]
    except Exception:
        detail = ""
    log.error("LLM HTTP %s: %s", resp.status_code, detail)
    probe = RuntimeError("HTTP %s %s" % (resp.status_code, detail))
    raise LLMError(friendly_error(probe), detail or str(probe))


def _first_choice(data: dict) -> dict:
    """兼容 choices 缺失/为空/带 error 体的响应，避免 KeyError 或 IndexError。"""
    if not isinstance(data, dict):
        raise LLMError("模型服务返回异常，请稍后再试", str(data)[:300])
    err = data.get("error")
    if err:
        detail = json.dumps(err, ensure_ascii=False)[:300]
        log.warning("LLM 返回 error 体: %s", detail)
        raise LLMError(friendly_error(RuntimeError(detail)), detail)
    choices = data.get("choices") or []
    if not choices:
        raise LLMError("模型没有返回内容，请重试一次", json.dumps(data, ensure_ascii=False)[:300])
    return choices[0]


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
        "max_tokens": _max_tokens_for(model),
    }
    if tools:
        payload["tools"] = tools

    with httpx.Client(timeout=45) as client:
        resp = client.post(
            LLM_API_URL, json=payload,
            headers={"Authorization": f"Bearer {LLM_API_KEY}", "Content-Type": "application/json"},
        )
        _raise_for_status(resp)
        data = resp.json()

    choice = _first_choice(data)
    message = choice.get("message") or {}
    return {
        "content": message.get("content", "") or "",
        "tool_calls": message.get("tool_calls") or [],
        "usage": data.get("usage") or {},
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
        "max_tokens": _max_tokens_for(model),
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
            _raise_for_status(resp)
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
                if chunk.get("error"):
                    raise LLMError(friendly_error(RuntimeError(str(chunk["error"]))),
                                   json.dumps(chunk["error"], ensure_ascii=False)[:300])
                choices = chunk.get("choices") or [{}]     # 尾片可能只有 usage 没有 choices
                yield {
                    "delta": (choices[0] or {}).get("delta", {}) or {},
                    "finish_reason": choices[0].get("finish_reason"),
                    "usage": chunk.get("usage") or {},
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