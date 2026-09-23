import os
import base64
from sqlalchemy.orm import Session
from app.agent.llm import call_llm, stream_llm
from app.agent.memory import get_history
from app.agent.tools.registry import get_tool_definitions, execute_tool
from app.core.config import UPLOAD_DIR

SYSTEM_PROMPT = (
    "你是一个名叫「抠门达人」的省钱助手，性格幽默亲切。"
    "你的目标是帮用户用最少的钱过最好的生活。"
    "你擅长：推荐省钱菜谱、给出购物比价建议、分析消费账单、回答省钱攻略。"
    "回答要简洁实用，多用 emoji，适当幽默。"
)

# 多智能体注册表：每位专家有自己的系统人设 + 可用工具白名单
# tools=None 表示可用全部工具
AGENTS = {
    "default": {
        "name": "抠门达人",
        "system_prompt": SYSTEM_PROMPT,
        "tools": None,
    },
    "coupon": {
        "name": "优惠情报员",
        "system_prompt": (
            "你是「优惠情报员」，专门帮用户挖掘最近最划算的省钱优惠：推荐优惠活动、"
            "跨平台比价、抓住降价时机。回答简洁直接，先告诉用户「现在最值得薅的羊毛」，"
            "再具体到平台和价格，多用 emoji。"
        ),
        "tools": ["coupon_advice", "price_compare", "shopping_advice"],
    },
    "budget": {
        "name": "理财管家",
        "system_prompt": (
            "你是「理财管家」，帮用户管理月度预算和省钱目标：分析账单、查看省钱目标达成、"
            "给出预算控制与理财建议。用户口述消费（如「昨晚外卖32」）时，用 add_bill 帮他记账。"
            "谈消费情况必须先调用工具拿真实账单，引用具体金额和占比，绝不编造数字。"
            "语气专业但不严厉，多给可落地的省钱小技巧。"
        ),
        "tools": ["budget_advice", "analyze_bills", "add_bill"],
    },
}


def _agent_prompt(name: str) -> str:
    # 取某专家的系统人设，未知时回退默认
    return AGENTS.get(name, AGENTS["default"])["system_prompt"]


def _agent_tools(name: str) -> list:
    # 取某专家可用工具定义（按白名单过滤）；None 表示全部
    info = AGENTS.get(name, AGENTS["default"])
    whitelist = info["tools"]
    if whitelist is None:
        return get_tool_definitions()
    names = set(whitelist)
    return [d for d in get_tool_definitions() if d["function"]["name"] in names]


def run_agent(user_id: int, message: str, db: Session, agent: str = "default") -> tuple:
    # Agent 主流程（非流式，兼容/测试用）
    # 返回：(reply: str, tool_used: str)
    try:
        history = get_history(user_id, db)

        messages = [{"role": "system", "content": _agent_prompt(agent)}]
        messages.extend(history)
        messages.append({"role": "user", "content": message})

        tools = _agent_tools(agent)
        result = call_llm(messages, tools)

        if result["tool_calls"]:
            tool_call = result["tool_calls"][0]
            tool_name = tool_call["function"]["name"]
            tool_args = tool_call["function"]["arguments"]

            tool_result, is_final = execute_tool(tool_name, tool_args, user_id, db)

            # 生成型工具（菜谱/购物等）已产出完整回复，直接返回，跳过二次 LLM 加速
            if is_final:
                return tool_result, tool_name

            messages.append({
                "role": "assistant",
                "content": "",
                "tool_calls": [tool_call],
            })
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call["id"],
                "content": tool_result,
            })
            final = call_llm(messages)
            return final["content"], tool_name

        return result["content"], "chat"

    except Exception as e:
        return f"AI 助手暂时无法响应（{str(e)}），请稍后重试~", "error"


def run_agent_stream(user_id: int, message: str, db: Session, image_refs=None, agent: str = "default"):
    # Agent 主流程（流式）
    # 生成器，逐条 yield 事件：
    #   {"type":"chunk","text": str}           流式文本片段
    #   {"type":"meta","tool_used": str}       标记本次用了哪个工具
    #   {"type":"done"}                         结束标记
    try:
        history = get_history(user_id, db)

        messages = [{"role": "system", "content": _agent_prompt(agent)}]
        messages.extend(history)
        messages.append({"role": "user", "content": _build_user_content(message, image_refs)})
        tools = _agent_tools(agent)

        tool_call = None
        for evt in _stream_pass(messages, tools):
            if evt["type"] == "toolcall":
                tool_call = evt["tool_call"]
                break
            yield evt  # chunk

        # 没有触发工具：已把整段回复流式返回
        if not tool_call:
            yield {"type": "done"}
            return

        tool_name = tool_call["function"]["name"]
        tool_args = tool_call["function"]["arguments"]
        yield {"type": "meta", "tool_used": tool_name}

        tool_result, is_final = execute_tool(tool_name, tool_args, user_id, db)

        if is_final:
            # 生成型工具已产出完整回复
            yield {"type": "chunk", "text": tool_result}
            yield {"type": "done"}
            return

        messages.append({
            "role": "assistant",
            "content": "",
            "tool_calls": [tool_call],
        })
        messages.append({
            "role": "tool",
            "tool_call_id": tool_call["id"],
            "content": tool_result,
        })
        for evt in _stream_pass(messages, None):
            if evt["type"] == "chunk":
                yield evt
        yield {"type": "done"}

    except Exception as e:
        yield {"type": "chunk", "text": f"AI 助手暂时无法响应（{str(e)}），请稍后重试~"}
        yield {"type": "done"}


def _stream_pass(messages: list, tools: list = None):
    # 流式转发一轮 LLM，yield chunk 事件；若检测到工具调用则 yield toolcall 事件
    acc = {}
    order = []
    for evt in stream_llm(messages, tools):
        delta = evt["delta"] or {}
        text = delta.get("content")
        if text:
            yield {"type": "chunk", "text": text}
        for tc in delta.get("tool_calls") or []:
            idx = tc.get("index", 0)
            if idx not in acc:
                acc[idx] = {"id": "", "name": "", "arguments": ""}
                order.append(idx)
            entry = acc[idx]
            src = tc.get("id")
            if src:
                entry["id"] = src
            fn = tc.get("function") or {}
            if fn.get("name"):
                entry["name"] = fn.get("name")
            if fn.get("arguments"):
                entry["arguments"] += fn.get("arguments")
        if evt["finish_reason"] == "tool_calls":
            break
        if evt["finish_reason"] in ("stop", "length"):
            break
    if order:
        e = acc[order[0]]
        if e["name"]:
            yield {
                "type": "toolcall",
                "tool_call": {
                    "id": e["id"],
                    "type": "function",
                    "function": {"name": e["name"], "arguments": e["arguments"]},
                },
            }
            return
    return


def _build_user_content(message: str, image_refs):
    # 若用户上传了图片，把消息组装成多模态格式（文本 + 图片）
    if not image_refs:
        return message
    parts = [{"type": "text", "text": message}]
    for ref in image_refs:
        parts.append({"type": "image_url", "image_url": {"url": _resolve_image(ref)}})
    return parts


def _resolve_image(ref: str) -> str:
    # 本地上传的图片 → base64 data URL（模型服务器无法访问 localhost）
    # 其它 http/data 链接原样返回
    ref = (ref or "").strip()
    if ref.startswith(("http://", "https://", "data:")):
        return ref
    path = os.path.join(UPLOAD_DIR, os.path.basename(ref))
    if os.path.exists(path):
        ext = os.path.splitext(path)[1].lower().lstrip(".")
        mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "gif": "gif", "webp": "webp"}.get(ext, "jpeg")
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        return f"data:image/{mime};base64,{b64}"
    return ref