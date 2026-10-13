from app.agent.tools.registry import register_tool, make_table, ToolResult


@register_tool(
    name="coupon_advice",
    final=True,
    description="推荐近期可用的省钱优惠活动（外卖/话费/银行/购物等平台），帮用户薅最近的羊毛",
    parameters={
        "max_items": {"type": "integer", "description": "最多返回几条活动，默认5"},
    },
)
def coupon_advice(max_items: int = 5, user_id: int = 0, db=None, **kwargs):
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
    table_rows = []
    for r in rows:
        line = "- " + (r.platform or "通用") + " · " + (r.title or "")
        if getattr(r, "deadline", None):
            line += "（截止 " + r.deadline.strftime("%m-%d") + "）"
        L.append(line)
        if getattr(r, "content", ""):
            L.append("   " + r.content)
        table_rows.append([r.platform or "通用", r.title or "",
                           r.deadline.strftime("%m-%d") if getattr(r, "deadline", None) else "长期",
                           "已验证" if getattr(r, "verified", 0) else "待核实"])
    L.append("")
    L.append("（信息来自活动库，使用前可再复核下具体规则~）")
    L.append("活动清单已经用表格展示给用户了，正文只挑 1-2 条最值得薅的展开讲，不要把表格逐条念一遍。")
    return ToolResult("\n".join(L), [],
                      [make_table("现在最值得薅的羊毛", ["平台", "活动", "截止", "可信度"], table_rows)])


def _price_table(res: dict) -> dict:
    """比价结果表：手机端放得下四列，商品名进标题而不是每行重复。"""
    items = res["items"][:6]
    rows = []
    for it in items:
        final = it.get("final_price") or 0
        was = it.get("price") or 0
        cut = round(was - final, 2) if was > final else (it.get("coupon_amount") or 0)
        rows.append([
            it["platform"],
            "¥%.2f" % final,
            ("省 %.2f" % cut) if cut else "—",
            (it.get("shop") or ("站内记录" if it.get("source") == "站内库" else "—"))[:12],
        ])
    low = res["lowest"]
    note = []
    if low:
        note.append("最低：%s ¥%.2f" % (low["platform"], low["final_price"]))
    if res["spread"]:
        note.append("最高最低差 ¥%.2f" % res["spread"])
    if res["budget"] and low:
        gap = res["budget"] - low["final_price"]
        note.append(("预算内，余 ¥%.2f" % gap) if gap >= 0 else ("超预算 ¥%.2f" % -gap))
    return make_table(
        "比价：%s" % (res["keyword"] or "该商品"),
        ["平台", "到手价", "优惠", "店铺"], rows,
        "｜".join(note) + ("" if res["live"] else "｜价格为站内记录，非实时"))


@register_tool(
    name="price_compare",
    description=("比价：把商品名拿去京东/天猫查实时到手价，返回店铺、券、可跳转购买链接。"
                 "用户说「帮我比下这个」「XX 哪家便宜」「这个链接值不值得买」时调用。"
                 "商品名放进 product；用户发的是链接或整段分享文案时，把原文一字不改地放进 link，"
                 "系统会自己从中抽商品名。"),
    parameters={
        "product": {"type": "string", "description": "商品名称关键词，例如：小米15 手机"},
        "link": {"type": "string", "description": "用户发的商品链接或整段分享文案，没有就留空"},
        "budget": {"type": "number", "description": "用户预算（元），没有就留空"},
    },
)
def price_compare(product: str = "", link: str = "", budget=None,
                  user_id: int = 0, db=None, **kwargs):
    from app.services.price_service import compare

    # 实测模型会把链接单独抄进 link、把「」里的商品标题丢掉，于是解析不出商品名。
    # 所以无条件把本轮原话并进来（product 非空时它优先，不会被这段影响），
    # 而不是把正确性押在模型有没有抄全参数上。
    ctx = kwargs.get("context") or {}
    extra = (ctx.get("message") or "").strip()
    if extra and extra not in (link or ""):
        link = " ".join(x for x in (link, extra) if x).strip()

    res = compare(keyword=product, link=link, budget=budget, db=db)
    items, links, warnings = res["items"], res["links"], res["warnings"]

    if not items:
        # 一条真实价格都没有。这时仍然把各平台搜索入口给出去（卡片照样有用），
        # 但要把原因原样交回去，禁止模型凭空评价贵贱。
        why = "；".join(warnings) or "没查到任何价格"
        text = ("比价失败：" + why +
                "\n\n现在手上没有任何价格数据。请如实告诉用户这次查不到价格，并按上面的原因说明"
                "（常见是：只发了链接没发商品名、属于服装鞋包等不支持比价的品类、或该品牌不在数据源里）。"
                "请用户复制商品标题发来再比。禁止在没有数据时说贵不贵、值不值得买。")
        if links:
            text += "\n已经给了用户各平台「搜同款」入口卡片，可以提醒他自己点开看价。"
        return ToolResult(text, links)

    L = []
    if res["from_link"]:
        L.append("[链接解读] 平台：%s；商品ID：%s；从中识别到的商品名：%s" % (
            res["platform_hint"] or "未知", res["goods_id"] or "未取到", res["keyword"] or "未取到"))
    L.append("[比价结果] %s" % (res["keyword"] or "（只有商品链接，没有商品名）"))
    L.append("各渠道到手价（低→高）：")
    for it in items[:6]:
        seg = "- %s %s 元｜%s" % (
            it["platform"], "%.2f" % (it.get("final_price") or 0), (it.get("title") or "")[:28])
        note = []
        if it.get("shop"):
            note.append(it["shop"])
        if it.get("price") and it.get("final_price") and it["price"] > it["final_price"]:
            note.append("原价 %.2f，省 %.2f" % (it["price"], it["price"] - it["final_price"]))
        if it.get("coupon_amount"):
            note.append("券 %.2f" % it["coupon_amount"])
        if it.get("rating"):
            note.append("好评率 %s%%" % it["rating"])
        if it.get("source") == "站内库":
            note.append("站内记录 %s" % (it.get("recorded_at") or "近期"))
        if note:
            seg += "（" + "、".join(note) + "）"
        L.append(seg)
    low = res["lowest"]
    if low:
        L.append("最低：%s %.2f 元（%s）" % (low["platform"], low["final_price"], low.get("shop") or "店铺未知"))
    if res["spread"]:
        L.append("最高最低差 %.2f 元，值得挑平台" % res["spread"])
    if res["hist_low"] and low:
        cur = low.get("final_price") or 0
        L.append("站内记录的历史最低价 %.2f 元，当前 %s" % (
            res["hist_low"], "接近历史低价，可以下手" if cur <= res["hist_low"] * 1.05
            else "比历史低价高 %.2f 元，不急可以再等等" % (cur - res["hist_low"])))
    if res["budget"] and low:
        gap = res["budget"] - low["final_price"]
        L.append("预算 %.2f 元：%s" % (res["budget"],
                 "在预算内，还余 %.2f 元" % gap if gap >= 0 else "超预算 %.2f 元，建议换型号或等活动" % -gap))
    if not res["live"]:
        L.append("注意：以上价格全部来自站内记录，没有拿到实时价。")
    if warnings:
        L.append("")
        L.append("数据缺口：" + "；".join(warnings))
    L.append("")
    L.append("比价表格已经由界面直接渲染给用户了，正文里不要再逐条复述一遍数字。"
             "请按三步回答用户：1) 比的是什么商品；2) 哪个平台哪个店铺更便宜、便宜多少（"
             "只引用上面出现过的数字，一条都不许自己加）；3) 为什么选它（到手价、券、店铺、"
             "是否接近历史低价、是否在预算内）。"
             "特别注意：上面没有「站内记录的历史最低价」这一行时，绝对不要提历史低价、"
             "最近最低、降价时机这类话，那是没有的数据（实测模型会自己补这句）。"
             "有数据缺口的要如实说明，比如京东今天查不到就讲清楚只有天猫。"
             "购买入口已经用卡片展示，正文不要贴网址、不要用 [文字](链接) 的 Markdown 语法。")
    return ToolResult("\n".join(L), links, [_price_table(res)])