from sqlalchemy.orm import Session
from app.agent.llm import call_llm
from app.agent.memory import get_history
from app.agent.tools.registry import get_tool_definitions, execute_tool

SYSTEM_PROMPT = (
    "你是一个名叫「抠门达人」的省钱助手，性格幽默亲切。"
    "你的目标是帮用户用最少的钱过最好的生活。"
    "你擅长：推荐省钱菜谱、给出购物比价建议、分析消费账单、回答省钱攻略。"
    "回答要简洁实用，多用 emoji，适当幽默。"
)


def run_agent(user_id: int, message: str, db: Session) -> tuple:
    # Agent 主流程
    # 返回：(reply: str, tool_used: str)
    try:
        history = get_history(user_id, db)

        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(history)
        messages.append({"role": "user", "content": message})

        tools = get_tool_definitions()
        result = call_llm(messages, tools)

        if result["tool_calls"]:
            tool_call = result["tool_calls"][0]
            tool_name = tool_call["function"]["name"]
            tool_args = tool_call["function"]["arguments"]

            tool_result = execute_tool(tool_name, tool_args, user_id, db)

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
