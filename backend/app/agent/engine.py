import logging
import os
import base64
from sqlalchemy.orm import Session
from app.agent.llm import call_llm, stream_llm, friendly_error, LLMError
from app.agent.memory import get_history
from app.agent.roles import DEFAULT_AGENT, normalize as normalize_agent
from app.agent.tools.registry import get_tool_definitions, execute_tool
from app.core.config import UPLOAD_DIR

log = logging.getLogger("agent")

# 多智能体注册表：每位专家有自己的系统人设 + 可用工具白名单。
# 只有两位专家（见 app/agent/roles.py）；回答以表格为主、正文只留一两句结论。
REPLY_RULES = (
    "回答格式要求（重要）：只要工具返回了 [表格] 段落，就把表格原样交给界面展示，"
    "正文只写一两句结论（选哪个、为什么、省多少），不要把表格内容再用文字复述一遍。"
    "没有表格时才用短段落，最多 3 行，能一行说清就一行。禁止输出网址和 Markdown 链接语法。"
)

AGENTS = {
    "coupon": {
        "name": "优惠情报员",
        "system_prompt": (
            "你是「优惠情报员」，专门帮用户挖掘最近最划算的省钱优惠：推荐优惠活动、"
            "跨平台比价、抓住降价时机。回答简洁直接。"
            "问优惠活动时先说「现在最值得薅的羊毛」再给平台和价格；"
            "问某个商品在哪买划算时直接给比价结论，不要套羊毛开场白。"
            "比价走京东/天猫实时数据：用户只发链接时先让他复制商品标题，"
            "服装鞋包饰品等非标品不支持比价，直说不支持、不要硬编价格。"
        ) + REPLY_RULES,
        "tools": ["coupon_advice", "price_compare", "shopping_advice"],
    },
    "budget": {
        "name": "理财管家",
        "system_prompt": (
            "你是「理财管家」，帮用户管理月度预算和省钱目标：分析账单、查看省钱目标达成、"
            "给出预算控制与理财建议。用户口述消费（如「昨晚外卖32」）时，用 add_bill 帮他记账。"
            "谈消费情况必须先调用工具拿真实账单，引用具体金额和占比，绝不编造数字。"
            "语气专业但不严厉，多给可落地的省钱小技巧。"
        ) + REPLY_RULES,
        "tools": ["budget_advice", "analyze_bills", "add_bill"],
    },
}


def _agent_prompt(name: str) -> str:
    return AGENTS[normalize_agent(name)]["system_prompt"]


def _agent_tools(name: str) -> list:
    # 取某专家可用工具定义（按白名单过滤）；None 表示全部
    info = AGENTS[normalize_agent(name)]
    whitelist = info["tools"]
    if whitelist is None:
        return get_tool_definitions()
    names = set(whitelist)
    return [d for d in get_tool_definitions() if d["function"]["name"] in names]


# 视觉模型 glm-4v-flash 实测不会返回 tool_calls（同一条强制指令，文本模型会调工具，
# 它只会把「Step 1: 调用 analyze_bills」当成话说出来），所以带图的对话拆两步走：
# 先让视觉模型把图抄成文字，再把这段文字并回用户消息，交给会调工具的文本模型。
VISION_TRANSCRIBE_PROMPT = (
    "你是图片转文字工具。把图片里的商品名、品牌、型号、金额、日期、规格等关键信息"
    "逐条原样抄出来，用短句列。"
    "看不清的部分直接跳过不写，禁止推测、补全、评价价格或回答图里的问题。"
)


def _vision_to_text(message: str, image_refs) -> str:
    """带图时先把图转成文字；转不出来也要留话，别让主模型以为用户没发图。"""
    content = _build_user_content(message, image_refs)
    if isinstance(content, str):
        return message
    try:
        got = (call_llm([{"role": "system", "content": VISION_TRANSCRIBE_PROMPT},
                         {"role": "user", "content": content}])["content"] or "").strip()
    except Exception:
        log.exception("图片转文字失败")
        got = ""
    if not got:
        return message + "\n[图片识别失败] 这次没读出图片内容，请如实告诉用户" \
                         "可以重新上传或直接打字说明，不要假装看到了图里的东西。"
    return message + "\n[下面是视觉模型抄录的图片内容，可能有错，只当参考] " + got


def _with_link_hint(message: str) -> str:
    # 引擎每轮只调一次工具，所以链接解析不做成工具，直接算好附在消息里，
    # 省掉一次工具调用，模型才有余地把链接原样填进 price_compare 的参数
    if not message or "http" not in message:
        return message
    try:
        from app.services.link_resolver import resolve
        p = resolve(message)
    except Exception:
        return message
    bits = []
    if p.get("platform"):
        bits.append("平台=%s" % p["platform"])
    if p.get("goods_id"):
        bits.append("商品ID=%s" % p["goods_id"])
    if p.get("keyword"):
        bits.append("商品名候选=%s" % p["keyword"])
    if not bits:
        return message
    hint = "[系统解析链接] " + "，".join(bits) + "。"
    if p.get("keyword"):
        hint += "比价请调用 price_compare，product 参数填「%s」，link 参数填用户那条链接原文。" % p["keyword"]
    else:
        hint += "比价请调用 price_compare，product 参数从上文找出商品名填进来，link 参数填用户那条链接原文。"
    return message + "\n" + hint


def _error_text(e: Exception) -> str:
    # LLMError 的 brief 本身就是一句完整的人话，再套「暂时无法响应…请稍后重试」会自相矛盾
    # （图片已失效这种事重试一百次也一样），所以原样回。
    if isinstance(e, LLMError):
        return e.brief
    return "AI 助手暂时无法响应（%s），请稍后重试~" % friendly_error(e)


def run_agent(user_id: int, message: str, db: Session, agent: str = DEFAULT_AGENT) -> tuple:
    # Agent 主流程（非流式，兼容/测试用）
    # 返回：(reply: str, tool_used: str)
    try:
        history = get_history(user_id, db, agent)

        messages = [{"role": "system", "content": _agent_prompt(agent)}]
        messages.extend(history)
        messages.append({"role": "user", "content": _with_link_hint(message)})

        tools = _agent_tools(agent)
        result = call_llm(messages, tools)

        if result["tool_calls"]:
            tool_call = result["tool_calls"][0]
            tool_name = tool_call["function"]["name"]
            tool_args = tool_call["function"]["arguments"]

            tool_result, is_final, _, _ = execute_tool(tool_name, tool_args, user_id, db,
                                                       context={"message": message})

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
        log.exception("Agent 调用失败")
        return _error_text(e), "error"


def run_agent_stream(user_id: int, message: str, db: Session, image_refs=None,
                     agent: str = DEFAULT_AGENT):
    # Agent 主流程（流式）
    # 生成器，逐条 yield 事件：
    #   {"type":"chunk","text": str}           流式文本片段
    #   {"type":"meta","tool_used": str}       标记本次用了哪个工具
    #   {"type":"tables","items": [...]}        工具产出的结构化表格（前端渲染成表格）
    #   {"type":"links","items": [...]}         工具产出的可跳转链接（前端渲染成卡片）
    #   {"type":"done"}                         结束标记
    try:
        history = get_history(user_id, db, agent)

        messages = [{"role": "system", "content": _agent_prompt(agent)}]
        messages.extend(history)
        user_text = _with_link_hint(message)
        if image_refs:
            user_text = _vision_to_text(user_text, image_refs)
        messages.append({"role": "user", "content": user_text})
        tools = _agent_tools(agent)

        tool_call = None
        tokens = 0
        for evt in _stream_pass(messages, tools):
            if evt["type"] == "toolcall":
                tool_call = evt["tool_call"]
                break
            if evt["type"] == "usage":
                tokens += int(evt["usage"].get("total_tokens") or 0)
                continue
            yield evt  # chunk

        # 没有触发工具：已把整段回复流式返回
        if not tool_call:
            yield {"type": "done", "tokens_used": tokens}
            return

        tool_name = tool_call["function"]["name"]
        tool_args = tool_call["function"]["arguments"]
        yield {"type": "meta", "tool_used": tool_name}

        tool_result, is_final, links, tables = execute_tool(tool_name, tool_args, user_id, db,
                                                            context={"message": message})
        if tables:
            # 表格先出：用户第一眼看到的就是数字对比，文字结论随后跟上
            yield {"type": "tables", "items": tables}
        if links:
            # 先给卡片数据，让购买入口尽早出现，不必等文字生成完
            yield {"type": "links", "items": links}

        if is_final:
            # 生成型工具已产出完整回复
            yield {"type": "chunk", "text": tool_result}
            yield {"type": "done", "tokens_used": tokens}
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
            if evt["type"] == "usage":
                tokens += int(evt["usage"].get("total_tokens") or 0)
            elif evt["type"] == "chunk":
                yield evt
        yield {"type": "done", "tokens_used": tokens}

    except Exception as e:
        log.exception("Agent 流式调用失败")
        # 标记成 error：这轮回复不该被下一轮当成「我上次说过的话」读回给模型
        yield {"type": "meta", "tool_used": "error"}
        yield {"type": "chunk", "text": _error_text(e)}
        yield {"type": "done"}


def _stream_pass(messages: list, tools: list = None):
    # 流式转发一轮 LLM，yield chunk 事件；若检测到工具调用则 yield toolcall 事件
    acc = {}
    order = []
    usage = {}
    finished = None
    for evt in stream_llm(messages, tools):
        if evt.get("usage"):
            usage = evt["usage"]
        if finished:
            continue          # 已经拿到 finish_reason，只为把尾部的 usage 分片收干净
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
        if evt["finish_reason"] in ("tool_calls", "stop", "length"):
            finished = evt["finish_reason"]
    if usage:
        yield {"type": "usage", "usage": usage}
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
    # 文件已经不在上传目录（清过缓存、或前端传了错名字）时别把裸路径发给模型：
    # 只会换来一个 400，用户看到的是「服务暂时不可用」，根本不知道该重传图片
    raise LLMError("图片已失效，请重新上传后再发一次", "本地找不到图片文件: %s" % ref)