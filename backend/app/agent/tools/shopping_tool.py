from app.agent.tools.registry import register_tool
from app.agent.llm import call_llm_simple


@register_tool(
    name="shopping_advice",
    final=True,
    description="给出购物建议，包括品牌对比、省钱时机、避坑提示",
    parameters={
        "product": {
            "type": "string",
            "description": "想买的商品名称和预算，例如：2000元扫地机器人 家里有猫",
        },
    },
)
def shopping_advice(product: str, **kwargs) -> str:
    prompt = "用户想买：" + product + "。请给出结构化的省钱建议：1. 推荐品牌/型号（2-3 个）及各自优缺点 2. 合理价位区间（历史常见最低价） 3. 最佳购买时机（如双十一、618、品牌日） 4. 避坑提示（哪些配置不值得加钱） 5. 二手/替代方案（如果有）。用列表形式回复，要简洁。"
    system = "你是一个资深的比价达人，最擅长找到性价比最高的消费方案。"
    return call_llm_simple(prompt, system)