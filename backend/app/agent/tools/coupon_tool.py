from app.agent.tools.registry import register_tool


@register_tool(
    name="coupon_advice",
    final=True,
    description="推荐近期可用的省钱优惠活动（外卖/话费/银行/购物等平台），帮用户薅最近的羊毛",
    parameters={
        "max_items": {"type": "integer", "description": "最多返回几条活动，默认5"},
    },
)
def coupon_advice(max_items: int = 5, user_id: int = 0, db=None, **kwargs) -> str:
    if db is None:
        return "数据库不可用"
    from datetime import datetime
    from sqlalchemy import or_
    from app.models.coupon_activity import CouponActivity
    rows = (db.query(CouponActivity)
        .filter(or_(CouponActivity.deadline.is_(None), CouponActivity.deadline >= datetime.now()))
        .order_by(CouponActivity.verified.desc(), CouponActivity.created_at.desc())
        .limit(int(max_items)).all())
    if not rows:
        return "最近没有已收录的优惠活动，稍后再来看看~"
    L = ["[近期优惠情报]"]
    for r in rows:
        line = "- " + (r.platform or "通用") + " · " + (r.title or "")
        if getattr(r, "deadline", None):
            line += "（截止 " + r.deadline.strftime("%m-%d") + "）"
        L.append(line)
        if getattr(r, "content", ""):
            L.append("   " + r.content)
    L.append("")
    L.append("（信息来自活动库，使用前可再复核下具体规则~）")
    return "\n".join(L)


@register_tool(
    name="price_compare",
    final=True,
    description="查询某商品在各平台的比价与价格区间，帮用户找到最划算的购买渠道",
    parameters={
        "product": {"type": "string", "description": "商品名称关键词，例如：扫地机器人"},
    },
)
def price_compare(product: str = "", user_id: int = 0, db=None, **kwargs) -> str:
    if db is None:
        return "数据库不可用"
    product = (product or "").strip()
    if not product:
        return "请告诉我想比价的商品名称~"
    from app.models.price_history import PriceHistory
    rows = (db.query(PriceHistory)
        .filter(PriceHistory.product_name.like("%" + product + "%"))
        .order_by(PriceHistory.recorded_at.desc()).all())
    if not rows:
        return "暂未收录「" + product + "」的比价记录"
    by_platform = {}
    for r in rows:
        plat = r.platform or "未知"
        by_platform.setdefault(plat, []).append(float(r.price or 0))
    L = ["[比价情报] " + product]
    for plat, prices in by_platform.items():
        lo = min(prices)
        hi = max(prices)
        cur = prices[0]
        L.append("- " + plat + ": 当前 " + ("%.2f" % cur) + " 元 / 区间 " + ("%.2f" % lo) + " ~ " + ("%.2f" % hi) + " 元")
    low = min(float(r.price or 0) for r in rows)
    for r in rows:
        if float(r.price or 0) == low:
            L.append("")
            L.append("[最划算] " + (r.platform or "") + " 约 " + ("%.2f" % low) + " 元，可参考~")
            break
    return "\n".join(L)