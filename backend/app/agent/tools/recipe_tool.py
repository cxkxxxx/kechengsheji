from app.agent.tools.registry import register_tool
from app.agent.llm import call_llm_simple


@register_tool(
    name="generate_recipe",
    description="根据用户提供的现有食材，生成省钱的菜谱并估算成本",
    parameters={
        "ingredients": {
            "type": "string",
            "description": "现有的食材，用逗号分隔，例如：土豆,青椒,鸡蛋",
        },
    },
)
def generate_recipe(ingredients: str, **kwargs) -> str:
    prompt = "我手头有以下食材：" + ingredients + "。请基于这些食材设计 2-3 个省钱菜谱（不需要额外买太多配料）。每个菜谱包含：菜名、做法步骤、估算成本（元）。如果缺少关键配料，也请给出替代建议。最后给出 1 条食材保存的小妙招。"
    system = "你是一个会过日子的家庭大厨，擅长用现有食材做出便宜又好吃的饭菜。"
    return call_llm_simple(prompt, system)