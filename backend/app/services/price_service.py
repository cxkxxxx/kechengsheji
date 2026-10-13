"""商品比价编排。

两层数据源，逐层降级：
1. 京东/天猫实时比价（best-price-mcp，第三方中转，见 app/services/best_price.py 的风险说明）
2. 站内 price_history 表（管理员或用户补录）——各平台价与历史区间

给前端的卡片只放**查到价格的**商品链接。各平台「搜同款」直达入口以前也下发成卡片，
但那种卡片点开没有价格、和商品也不对应，用户反馈是噪音，所以不再产出；
查不到价格时由工具如实说明原因并请用户补商品名。
"""
from app.services import best_price
from app.services.link_resolver import resolve
from app.models.price_history import PriceHistory


def _priced_links(items: list) -> list:
    """只有带到手价的商品链接才值得做成卡片，按价格从低到高排。"""
    out = []
    for it in items:
        price = it.get("final_price")
        if not (price and it.get("url")):
            continue
        out.append({"platform": it["platform"],
                    "label": "%s·%s" % (it["platform"], it.get("shop") or "商品页"),
                    "url": it["url"], "kind": "product", "price": price})
    return out


def _local_rows(db, keyword: str, limit: int = 30) -> list:
    if db is None or not keyword:
        return []
    like = "%" + keyword.replace("%", r"\%").replace("_", r"\_") + "%"
    return (db.query(PriceHistory)
            .filter(PriceHistory.product_name.like(like))
            .order_by(PriceHistory.recorded_at.desc())
            .limit(limit).all())


def _from_local(db, keyword: str) -> list:
    """站内价格库：同平台取最近一条，顺带算出历史最低/最高。"""
    rows = _local_rows(db, keyword)
    if not rows:
        return []
    by_platform = {}
    for r in rows:
        p = r.platform or "其他"
        price = float(r.price or 0)
        stat = by_platform.setdefault(p, {"latest": price, "low": price, "high": price,
                                          "name": r.product_name, "url": r.url, "when": r.recorded_at})
        stat["latest"] = price                      # 已按时间倒序，最后写入的就是最近一条
        stat["low"] = min(stat["low"], price)
        stat["high"] = max(stat["high"], price)
    out = []
    for p, s in by_platform.items():
        out.append({"platform": p, "title": s["name"], "price": round(s["latest"], 2),
                    "final_price": round(s["latest"], 2), "hist_low": round(s["low"], 2),
                    "hist_high": round(s["high"], 2), "url": s["url"] or "",
                    "source": "站内库", "recorded_at": str(s["when"])[:10] if s["when"] else ""})
    out.sort(key=lambda x: x["final_price"])
    return out


def compare(keyword: str = "", link: str = "", budget=None, db=None, limit: int = 6) -> dict:
    text = " ".join(x for x in (link, keyword) if x)
    parsed = resolve(text)
    # best-price 读不了商品链接（它自己的提示就是「请复制商品标题」），
    # 所以链接只能靠 link_resolver 抽出商品名，抽不出来就没有实时价格。
    kw = (keyword or "").strip() or parsed.get("keyword") or ""
    kw = kw.strip(" 【】「」")[:40]
    goods_id = parsed.get("goods_id") or ""

    live, warnings = best_price.search(kw, limit=limit) if kw else ([], [])
    local = _from_local(db, kw)
    items = live + [x for x in local if x["platform"] not in {i["platform"] for i in live}]
    items.sort(key=lambda x: x.get("final_price") or 10 ** 9)

    if not kw and not goods_id:
        return {"keyword": "", "from_link": bool(parsed.get("url")), "platform_hint": parsed.get("platform") or "",
                "goods_id": "", "live": False, "items": [], "links": [], "lowest": None, "spread": 0,
                "hist_low": None, "budget": None,
                "warnings": ["没拿到商品名，不要对贵贱下结论；请让用户复制商品标题发过来"]}

    links = _priced_links(items)

    lowest = items[0] if items and items[0].get("final_price") else None
    hist_low = min([i["hist_low"] for i in local if i.get("hist_low")], default=None)
    try:
        budget_v = float(budget) if budget else None
    except (TypeError, ValueError):
        budget_v = None

    return {
        "keyword": kw,
        "from_link": bool(parsed.get("url")),
        "platform_hint": parsed.get("platform") or "",
        "goods_id": goods_id,
        "live": bool(live),
        "items": items,
        "links": links,
        "lowest": lowest,
        # items 已按到手价升序排，最高减最低才是价差（写反过一次的这里加个说明）
        "spread": round(items[-1]["final_price"] - items[0]["final_price"], 2)
                    if len(items) > 1 and items[-1].get("final_price") else 0,
        "hist_low": hist_low,
        "budget": budget_v,
        "warnings": warnings,
    }
