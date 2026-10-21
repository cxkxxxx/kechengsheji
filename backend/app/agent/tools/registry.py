import inspect
import json
import logging

log = logging.getLogger("agent.tools")

# 全局工具注册表
_TOOLS = {}
# 生成型工具：结果已是完整回复，无需再次经 LLM 总结
_FINAL_TOOLS = set()


def _required_params(func, parameters: dict) -> list:
    # 形参里没有默认值的那个才是必填（user_id/db/kwargs 由引擎注入，都有默认值，故天然排除）。
    # 曾经无脑把 parameters 全标 required，模型被迫为可选参数编造取值：
    # analyze_bills 的 month 被填成 2021-08 之类，账单永远查不到数据。
    sig = inspect.signature(func)
    return [
        p.name for p in sig.parameters.values()
        if p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD)
        and p.default is inspect.Parameter.empty
        and p.name in parameters
    ]


def register_tool(name, description, parameters, final=False):
    # 装饰器工厂：注册一个 AI 工具；final=True 表示结果是完整回复，跳过二次 LLM
    def decorator(func):
        _TOOLS[name] = {
            "function": func,
            "description": description,
            "parameters": parameters,
            "required": _required_params(func, parameters),
        }
        if final:
            _FINAL_TOOLS.add(name)
        return func
    return decorator


def get_tool_definitions() -> list:
    # 获取工具定义列表（OpenAI Function Calling 格式）
    result = []
    for name, info in _TOOLS.items():
        result.append({
            "type": "function",
            "function": {
                "name": name,
                "description": info["description"],
                "parameters": {
                    "type": "object",
                    "properties": info["parameters"],
                    "required": info["required"],
                },
            },
        })
    return result


class ToolResult:
    """工具返回值：给模型看的文本 + 给小程序渲染的结构化卡片和表格。

    tables 用「表头 + 字符串二维数组」而不是对象数组：小程序端 wx:for 直接套两层就出表格，
    不用每列都约定 key，工具侧也不容易拼错字段名。
    """

    def __init__(self, text: str, links=None, tables=None):
        self.text = text
        self.links = links or []
        self.tables = tables or []


def make_table(title: str, head: list, rows: list, note: str = "") -> dict:
    """拼一张表。单元格一律转成字符串，None 显示成「—」而不是「None」。"""
    return {
        "title": title,
        "head": [str(h) for h in head],
        "rows": [["—" if c is None else str(c) for c in r] for r in rows],
        "note": note,
    }


def execute_tool(name: str, args_str, user_id: int, db, context: dict = None):
    # 执行工具，返回 (结果字符串, 是否为完整回复, 可跳转链接列表, 表格列表)
    # context 是引擎知道的现场信息（目前只有本轮用户原文）。实测模型该填 link 参数时经常填
    # 空，把「抄对链接」这件事交给它不如让工具自己能拿到原文兜底。
    if name not in _TOOLS:
        return (f"工具 {name} 不存在", False, [], [])
    try:
        # args_str 可能是 dict 或 JSON 字符串
        if isinstance(args_str, dict):
            kwargs = args_str
        else:
            kwargs = json.loads(args_str)
    except Exception:
        kwargs = {}
    if not isinstance(kwargs, dict):
        kwargs = {}              # 模型也可能吐出 "null" 或一个数组，直接 ** 会 TypeError
    missing = [k for k in _TOOLS[name]["required"] if not kwargs.get(k)]
    if missing:
        # 把缺哪个参数说清楚，模型下一轮能自己纠正，而不是抛 TypeError 变成一堆乱码提示
        return ("缺少必填参数：" + "、".join(missing) + "，请带上该信息重新调用本工具", False, [], [])
    try:
        result = _TOOLS[name]["function"](**kwargs, user_id=user_id, db=db,
                                          context=context or {})
        if isinstance(result, ToolResult):
            return (str(result.text), name in _FINAL_TOOLS, result.links, result.tables)
        return (str(result), name in _FINAL_TOOLS, [], [])
    except Exception as e:
        log.exception("工具 %s 执行失败", name)
        return (f"工具执行错误：{str(e)}", False, [], [])


# 自动导入所有工具文件，触发注册
from app.agent.tools import (  # noqa: E402,F401
    recipe_tool, shopping_tool, bill_tool, knowledge_tool, coupon_tool, budget_tool, insight_tool)