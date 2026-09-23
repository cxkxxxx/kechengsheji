import inspect
import json

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


def execute_tool(name: str, args_str, user_id: int, db):
    # 执行工具，返回 (结果字符串, 是否为完整回复)
    if name not in _TOOLS:
        return (f"工具 {name} 不存在", False)
    try:
        # args_str 可能是 dict 或 JSON 字符串
        if isinstance(args_str, dict):
            kwargs = args_str
        else:
            kwargs = json.loads(args_str)
    except Exception:
        kwargs = {}
    missing = [k for k in _TOOLS[name]["required"] if not kwargs.get(k)]
    if missing:
        # 把缺哪个参数说清楚，模型下一轮能自己纠正，而不是抛 TypeError 变成一堆乱码提示
        return ("缺少必填参数：" + "、".join(missing) + "，请带上该信息重新调用本工具", False)
    try:
        result = _TOOLS[name]["function"](**kwargs, user_id=user_id, db=db)
        return (str(result), name in _FINAL_TOOLS)
    except Exception as e:
        return (f"工具执行错误：{str(e)}", False)


# 自动导入所有工具文件，触发注册
from app.agent.tools import recipe_tool, shopping_tool, bill_tool, knowledge_tool, coupon_tool, budget_tool  # noqa: E402,F401