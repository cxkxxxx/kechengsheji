import os
from app.agent.tools.registry import register_tool
from app.core.config import CHROMA_DB_PATH


@register_tool(
    name="search_knowledge",
    description="查询省钱攻略知识库，回答如何省钱的具体问题",
    parameters={
        "query": {
            "type": "string",
            "description": "用户想查询的省钱话题，例如：超市打折时间、外卖怎么点最划算",
        },
    },
)
def search_knowledge(query: str, **kwargs) -> str:
    # 工具：省钱知识库问答
    collection_dir = os.path.join(CHROMA_DB_PATH)
    has_data = False
    if os.path.exists(collection_dir):
        for root, dirs, files in os.walk(collection_dir):
            if files:
                has_data = True
                break
    if not has_data:
        tips = _builtin_tips(query)
        if tips: return tips
        lines = []
        lines.append("知识库还在完善中，这里给你几个通用省钱思路：")
        lines.append("1. 能二手不全新（衣服/家具/电子产品优先闲鱼）")
        lines.append("2. 外卖凑满减 + 红包 + 银行优惠，一顿饭最少能省 5-10 元")
        lines.append("3. 日用品按大包装买，折合单价更便宜")
        lines.append("4. 信用卡选择自己消费最多的类别（餐饮/购物/加油）来拿返现")
        lines.append("5. 购物前加到购物车放 24 小时，很多冲动消费会自动取消")
        return chr(10).join(lines)
    try:
        import chromadb
        client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
        col = client.get_or_create_collection("saving_tips")
        result = col.query(query_texts=[query], n_results=3)
        docs = result.get("documents", [[]])[0]
        if not docs: return "知识库中没找到相关内容。"
        return "以下是攻略库中最相关的 3 条：" + chr(10) + chr(10) + ("-"*3 + chr(10)).join(docs)
    except Exception as e:
        return "知识库查询失败：" + str(e)


def _builtin_tips(query: str) -> str:
    q = query.lower()
    data = [
        (["超市", "打折"], "超市购物省钱时间表：周二/周三会员日 8.5 折；晚上 8 点后面包、熟食半价；临期食品区有 3-5 折。"),
        (["外卖", "饿了么", "美团"], "外卖最省技巧：先搜隐藏红包+会员红包叠银行周三/周五5折；凑满减到刚好超过门槛；收货后写评价返金豆。"),
        (["咖啡", "星巴克", "瑞幸"], "咖啡省钱：瑞幸每天用券后 10 元以内；星巴克买一送一券在闲鱼买；Manner 自带杯减 5 元。"),
        (["信用卡", "权益", "返现"], "信用卡怎么选：餐饮党选交通银行（周五5折）；网购党选招商银行/中信；经常出差选航司联名卡。"),
        (["话费", "充话费", "充值"], "话费充值：每月 28 日三大运营商会员日有活动；支付宝/京东每月有随机立减；不要一次性充太多。"),
        (["加油", "汽油"], "加油省钱：办中石油/中石化卡逢 10 号优惠；高德/滴滴加油比加油站便宜 0.3-0.5 元/升。"),
        (["机票"], "机票怎么买：提前 30-45 天买最便宜；周二下午价格最低；用航司会员日买（如南航每月28日）。"),
        (["快递", "寄快递"], "寄快递省钱：闲鱼搜优惠代发（顺丰/京东 8 折起），或菜鸟裹裹周末优惠券。"),
    ]
    matched = []
    for keywords, tip in data:
        for k in keywords:
            if k in q:
                matched.append(tip)
                break
    if matched:
        return "以下是相关省钱攻略：" + chr(10) + chr(10) + (chr(10) + chr(10)).join(matched)
    return ""