"""模型调用链路的离线回归测试：max_tokens 夹取 + 异常文案映射。

都是纯函数，不联网、不花额度。glm-4v-flash 的 max_tokens 上限只有 1024，
配到 1200 会让带图的请求整体 400，所以这条必须有测试兜住。
运行：pytest tests/test_llm_errors.py
"""
import httpx

from app.agent import llm
from app.agent.llm import LLMError, friendly_error


def test_vision_max_tokens_is_clamped():
    # 视觉模型超限会被智谱拒绝（1210），这里必须夹到 1024 以内
    assert llm._max_tokens_for(llm.LLM_VISION_MODEL) <= llm.VISION_MAX_TOKENS


def test_text_model_keeps_configured_max_tokens(monkeypatch):
    monkeypatch.setattr(llm, "LLM_MAX_TOKENS", 1200)
    assert llm._max_tokens_for(llm.LLM_MODEL) == 1200


def test_vision_clamp_follows_config(monkeypatch):
    # 配置低于上限时原样使用，不要反过来把用户的值改大
    monkeypatch.setattr(llm, "LLM_MAX_TOKENS", 512)
    assert llm._max_tokens_for(llm.LLM_VISION_MODEL) == 512


def test_llm_error_keeps_its_own_brief():
    assert friendly_error(LLMError("模型没有返回内容，请重试一次")) == "模型没有返回内容，请重试一次"


def test_quota_error_maps_even_from_plain_runtime_error():
    assert "额度不足" in friendly_error(RuntimeError("HTTP 402 余额不足，请购买资源包"))


def test_param_error_is_not_reported_as_outage():
    # _raise_for_status 造的是 RuntimeError，曾经因为类型判断落进通用分支
    e = RuntimeError('HTTP 400 {"error":{"code":"1210","message":"max_tokens参数非法：限制数值范围[1,1024]"}}')
    assert friendly_error(e) == "模型请求参数配置有误，请联系管理员检查 .env"


def test_auth_and_rate_limit_messages():
    assert "鉴权失败" in friendly_error(httpx.HTTPStatusError(
        "Client error 401 Unauthorized", request=None, response=None))
    assert "过于频繁" in friendly_error(httpx.HTTPStatusError(
        "Client error 429 Too Many Requests", request=None, response=None))


def test_timeout_maps_to_its_own_message():
    assert friendly_error(httpx.ConnectTimeout("timed out")) == "模型响应超时，请稍后再试"


def test_unknown_error_stays_generic():
    assert friendly_error(ValueError("完全想不到的东西")) == "模型服务返回异常，请稍后再试"


def test_first_choice_rejects_error_body():
    try:
        llm._first_choice({"error": {"code": "1210", "message": "max_tokens参数非法"}})
    except LLMError as e:
        assert "参数" in e.brief
    else:
        raise AssertionError("error 体应该被转成 LLMError")


def test_first_choice_rejects_empty_choices():
    try:
        llm._first_choice({"choices": []})
    except LLMError as e:
        assert e.brief == "模型没有返回内容，请重试一次"
    else:
        raise AssertionError("空 choices 应该被转成 LLMError")
