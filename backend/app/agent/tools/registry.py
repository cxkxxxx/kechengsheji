import json

# 全局工具注册表
_TOOLS = {}


def register_tool(name, description, parameters):
    # 装饰器工厂：注册一个 AI 工具
    def decorator(func):
        _TOOLS[name] = {
            "function": func,
            "description": description,
            "parameters": parameters,
        }
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
                    "required": list(info["parameters"].keys()),
                },
            },
        })
    return result


def execute_tool(name: str, args_str, user_id: int, db) -> str:
    # 执行工具，返回结果字符串
    if name not in _TOOLS:
        return f"工具 {name} 不存在"
    try:
        # args_str 可能是 dict 或 JSON 字符串
        if isinstance(args_str, dict):
            kwargs = args_str
        else:
            kwargs = json.loads(args_str)
    except Exception:
        kwargs = {}
    try:
        result = _TOOLS[name]["function"](**kwargs, user_id=user_id, db=db)
        return str(result)
    except Exception as e:
        return f"工具执行错误：{str(e)}"


# 自动导入所有工具文件，触发注册
from app.agent.tools import recipe_tool, shopping_tool, bill_tool, knowledge_tool  # noqa: E402,F401
