import re as _re
from datetime import datetime, date, timedelta

from sqlalchemy import func

from app.agent.tools.registry import register_tool, make_table, ToolResult
from app.models.bill import Bill
from app.models.budget_plan import BudgetPlan

CATEGORIES = ["餐饮", "购物", "交通", "生活", "娱乐", "医疗", "其他"]

# 用户口述的说法 → 标准分类（前端饼图配色与 seed 数据都按这套分类走）
_CAT_SYNONYMS = {
    "餐饮": ["吃", "饭", "餐", "外卖", "奶茶", "咖啡", "零食", "食堂", "聚"],
    "购物": ["买", "购", "衣", "鞋", "数码", "淘宝", "京东", "拼多多", "超市"],
    "交通": ["车", "行", "地铁", "公交", "油", "打车", "高铁", "机票", "停车"],
    "生活": ["水电", "话费", "房租", "日用", "燃气", "物业", "宽带", "充电"],
    "娱乐": ["玩", "影", "游戏", "KTV", "演出", "门票", "会员", "旅游"],
    "医疗": ["药", "医", "看病", "体检", "牙", "挂号", "诊所"],
}


def _norm_month(month) -> str:
    # 规整成 YYYY-MM；拿不到合法月份就用当月，避免模型填的脏值直接进 SQL
    s = str(month or "").strip().replace("/", "-").replace(".", "-").replace("年", "-").replace("月", "")
    parts = [p for p in s.split("-") if p.strip()]
    if len(parts) >= 2:
        try:
            y, m = int(parts[0]), int(parts[1])
        except ValueError:
            return datetime.now().strftime("%Y-%m")
        if 1 <= m <= 12:
            return "%04d-%02d" % (y + 2000 if y < 100 else y, m)
    return datetime.now().strftime("%Y-%m")


def _prev_month(month: str) -> str:
    y, m = int(month[:4]), int(month[5:7])
    return "%04d-%02d" % (y - 1, 12) if m == 1 else "%04d-%02d" % (y, m - 1)


def _months_with_bills(sess, user_id: int) -> list:
    rows = (sess.query(func.date_format(Bill.bill_date, "%Y-%m"))
            .filter(Bill.user_id == user_id)
            .group_by(func.date_format(Bill.bill_date, "%Y-%m")).all())
    return sorted({r[0] for r in rows if r[0]})


def _cat_rows(sess, user_id: int, month: str):
    return (sess.query(Bill.category, func.sum(Bill.amount).label("total"), func.count(Bill.id).label("cnt"))
            .filter(Bill.user_id == user_id)
            .filter(func.date_format(Bill.bill_date, "%Y-%m") == month)
            .group_by(Bill.category).all())


def _month_total(sess, user_id: int, month: str) -> float:
    return float(sess.query(func.sum(Bill.amount))
                 .filter(Bill.user_id == user_id)
                 .filter(func.date_format(Bill.bill_date, "%Y-%m") == month)
                 .scalar() or 0)


@register_tool(
    name="analyze_bills",
    description=("查询用户指定月份的真实账单数据：总支出、日均、分类占比、大额明细、与上月环比、当月省钱目标达成情况。"
                 "用户问「我的账单/消费/花了多少/怎么省」这类问题时必须调用本工具，不要凭空推测。"
                 "不确定月份时留空（默认当月）。"),
    parameters={
        "month": {
            "type": "string",
            "description": "要分析的月份，格式 YYYY-MM。留空表示当月。",
        },
    },
)
def analyze_bills(month: str = "", user_id: int = 0, db=None, **kwargs):
    if db is None:
        return "数据库不可用"
    month = _norm_month(month)
    asked = month
    cats = _cat_rows(db, user_id, month)
    if not cats:
        # 引擎每轮只跑一次工具（第二次生成时不再带 tools），让模型「换个月份重试」是走不通的，
        # 所以这里直接回落到最近一个有数据的月份，一次把真实数字给出去。
        avail = _months_with_bills(db, user_id)
        if not avail:
            return (month + " 及以前都没有账单记录。请引导用户先在「账单」页记一笔，"
                    "或告诉用户可以说「帮我记一笔 外卖 32 元」由你直接记账。")
        month = avail[-1]
        cats = _cat_rows(db, user_id, month)
        if not cats:
            return "账单数据读取异常，请稍后再试。"

    total = sum(float(r.total or 0) for r in cats)
    count = sum(int(r.cnt or 0) for r in cats)
    days = (db.query(func.count(func.distinct(func.date(Bill.bill_date))))
            .filter(Bill.user_id == user_id)
            .filter(func.date_format(Bill.bill_date, "%Y-%m") == month).scalar()) or 1
    ranked = sorted(cats, key=lambda r: float(r.total or 0), reverse=True)

    L = ["[%s 真实账单] 支出 %.2f 元 / %d 笔 / 有消费 %d 天 / 日均 %.2f 元"
         % (month, total, count, days, total / days)]
    L.append("分类占比：")
    for r in ranked:
        amt = float(r.total or 0)
        L.append("- %s %.2f 元（%.0f%%，%d 笔）" % (r.category or "其他", amt, amt / total * 100 if total else 0, r.cnt))

    tops = (db.query(Bill).filter(Bill.user_id == user_id)
            .filter(func.date_format(Bill.bill_date, "%Y-%m") == month)
            .order_by(Bill.amount.desc()).limit(5).all())
    if tops:
        L.append("金额最高的几笔：")
        for b in tops:
            L.append("- %s %s %s元（%s）"
                     % (b.bill_date.strftime("%m-%d") if b.bill_date else "", b.category or "其他",
                        "%.2f" % float(b.amount or 0), b.source or "无备注"))

    prev = _prev_month(month)
    prev_total = _month_total(db, user_id, prev)
    if prev_total > 0:
        delta = total - prev_total
        L.append("环比：%s 支出 %.2f 元，本月%s %.2f 元（%s%.1f%%）"
                 % (prev, prev_total, "多花" if delta >= 0 else "少花", abs(delta),
                    "+" if delta >= 0 else "-", abs(delta) / prev_total * 100))
    else:
        L.append("环比：%s 没有账单数据，无法比较" % prev)

    plan = (db.query(BudgetPlan).filter(BudgetPlan.user_id == user_id, BudgetPlan.month == month).first())
    plan_limit = float(plan.spend_limit or 0) if plan else 0
    if plan and (plan.target_amount or plan_limit):
        if plan.target_amount:
            L.append("省钱目标：目标 %.2f 元，已省 %.2f 元（达成 %.0f%%），连续打卡 %d 天"
                     % (float(plan.target_amount or 0), float(plan.saved_amount or 0),
                        float(plan.saved_amount or 0) / float(plan.target_amount) * 100,
                        int(plan.checkin_days or 0)))
        if plan_limit:
            L.append("支出上限：上限 %.2f 元，已花 %.2f 元（用掉 %.0f%%），%s"
                     % (plan_limit, total, total / plan_limit * 100,
                        "已超支 %.2f 元" % (total - plan_limit) if total > plan_limit
                        else "还可花 %.2f 元" % (plan_limit - total)))
    else:
        L.append("本月目标：尚未设定（既没设省钱目标也没设支出上限）")

    big = [r for r in ranked if total > 0 and float(r.total or 0) / total >= 0.35]
    if big:
        L.append("提示：下列分类占比超过 35%%，是主要压缩空间：%s"
                 % "、".join("%s %.0f%%" % (r.category or "其他", float(r.total or 0) / total * 100) for r in big))
    else:
        L.append("提示：没有单一分类占比超过 35%，消费结构较分散")
    if asked != month:
        # 回落说明放在最后：写在开头会让下一轮模型只看到「没有账单」就拒绝作答
        L.append("补充：%s 没有任何记录，以上是该用户最近有数据的 %s，请照这份数据分析并告知用户。" % (asked, month))
    L.append("分类占比和大额明细已经由界面渲染成表格了，正文不要再把这些数字逐条复述一遍。")
    L.append("请基于以上真实数字给出 3-5 条可落地的省钱建议；回复时必须沿用上面的月份 %s，"
             "并引用具体金额或占比，不要改口、不要编造数据。" % month)

    tables = [make_table(
        "%s 分类占比" % month,
        ["分类", "金额", "占比", "笔数"],
        [[r.category or "其他", "¥%.2f" % float(r.total or 0),
          "%.0f%%" % (float(r.total or 0) / total * 100 if total else 0), r.cnt]
         for r in ranked],
        "合计 ¥%.2f｜%d 笔｜日均 ¥%.2f" % (total, count, total / days),
    )]
    if tops:
        tables.append(make_table(
            "金额最高的几笔", ["日期", "分类", "金额", "备注"],
            [[b.bill_date.strftime("%m-%d") if b.bill_date else "—", b.category or "其他",
              "¥%.2f" % float(b.amount or 0), b.source or "—"] for b in tops],
        ))
    if prev_total > 0:
        delta = total - prev_total
        tables.append(make_table(
            "环比", ["月份", "支出", "变化"],
            [[prev, "¥%.2f" % prev_total, "—"],
             [month, "¥%.2f" % total,
              "%s¥%.2f（%s%.1f%%）" % ("多花" if delta >= 0 else "少花", abs(delta),
                                      "+" if delta >= 0 else "-",
                                      abs(delta) / prev_total * 100)]],
        ))
    return ToolResult("\n".join(L), [], tables)


@register_tool(
    name="add_bill",
    final=True,
    description=("按用户口述把消费记录写入账单表（记账）。用户说「昨晚外卖32」「记一笔：打车 25 元，昨天」这类话时调用。"
                 "一句话里有多笔消费就一次传多条。金额、分类、日期都能从上下文推断时再调用；"
                 "信息不足以确定金额时先追问，不要猜。"),
    parameters={
        "bills": {
            "type": "array",
            "description": "待写入的账单条目",
            "items": {
                "type": "object",
                "properties": {
                    "amount": {"type": "number", "description": "金额（元），正数"},
                    "category": {"type": "string", "enum": CATEGORIES, "description": "消费分类"},
                    "source": {"type": "string", "description": "简短备注，例如 午餐、打车、超市日用品；读不出来就留空，别填「看不清」"},
                    "bill_date": {"type": "string", "description": "消费日期 YYYY-MM-DD；用户说「昨天/上周」时换算成具体日期，留空按今天"},
                },
                # source 不列进 required：列了就必须填点什么，模型会拿「看不清」这种占位符来占位
                "required": ["amount", "category"],
            },
        },
    },
)
def add_bill(bills, user_id: int = 0, db=None, **kwargs) -> str:
    if db is None:
        return "数据库不可用"
    items = bills if isinstance(bills, list) else [bills]
    today = date.today()
    saved, skipped = [], []
    for i, raw in enumerate(items):
        item = raw if isinstance(raw, dict) else {}
        amount = _as_amount(item.get("amount"))
        if amount is None:
            skipped.append("第 %d 条金额无效（%r）" % (i + 1, item.get("amount")))
            continue
        bill = Bill(
            user_id=user_id,
            amount=amount,
            category=_as_category(item.get("category")),
            source=_as_source(item.get("source")),
            bill_date=_as_date(item.get("bill_date")) or today,
        )
        db.add(bill)
        saved.append(bill)
    if not saved:
        return "一条都没记上：" + ("；".join(skipped) if skipped else "没解析出有效金额") + "。请把金额说清楚，例如「外卖 32 元」。"
    db.commit()

    month = today.strftime("%Y-%m")
    L = ["已记入 %d 笔消费：" % len(saved)]
    for b in saved:
        L.append("- %s %s %.2f 元%s" % (b.bill_date.strftime("%m-%d"), b.category, float(b.amount),
                                        "（" + b.source + "）" if b.source else ""))
    if skipped:
        L.append("未能记录：" + "；".join(skipped))
    L.append("本月（%s）累计支出 %.2f 元。" % (month, _month_total(db, user_id, month)))
    L.append("（记错了可以到「账单」页长按那条记录删除）")
    return "\n".join(L)


def _as_source(v):
    """备注里的占位符不当真：图片看不清时模型会往这里填「看不清」，落库就成了垃圾数据。"""
    s = str(v or "").strip()
    if s in ("", "看不清", "未知", "无", "没有", "N/A", "n/a", "-", "无备注"):
        return ""
    return s[:100]


def _as_amount(v):
    try:
        f = round(float(str(v).replace("元", "").replace("¥", "").strip()), 2)
    except (TypeError, ValueError):
        return None
    return f if 0 < f <= 10 ** 7 else None


def _as_category(v):
    v = str(v or "").strip()
    if not v:
        return "其他"
    if v in CATEGORIES:
        return v
    for c in CATEGORIES:                 # 「医疗」↔「看病」这类直接包含关系
        if c in v or v in c:
            return c
    for c, words in _CAT_SYNONYMS.items():
        if any(w in v for w in words):
            return c
    return "其他"


def _as_date(v):
    s = str(v or "").strip().replace("/", "-").replace(".", "-")
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m", "%m-%d"):
        try:
            d = datetime.strptime(s, fmt)
        except ValueError:
            continue
        return d.date() if fmt != "%m-%d" else d.date().replace(year=date.today().year)
    # 模型常把「昨天」原样传过来，这里兜底换算，别默默记成今天
    today = date.today()
    if "前天" in s:
        return today - timedelta(days=2)
    if "昨天" in s or "昨日" in s:
        return today - timedelta(days=1)
    if "今天" in s or "今日" in s:
        return today
    if "明天" in s:
        return today + timedelta(days=1)
    n = _re.search(r"(\d+)\s*天\s*前", s)
    if n:
        return today - timedelta(days=int(n.group(1)))
    return None
