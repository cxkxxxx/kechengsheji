"""账单洞察类工具：月末预测、固定支出识别、平替建议、月度复盘。

这四个都只读本地 bills / budget_plans，不依赖任何外部数据源，所以演示时不会被
best-price-mcp 的共享配额卡住（那个京东侧实测会整天返回「已达调用上限」）。
唯一的例外是 cheaper_alternative 里可选的比价增强，它拿不到就安静跳过。
"""
import calendar
from datetime import date, datetime

from sqlalchemy import func

from app.agent.tools.registry import register_tool, make_table, ToolResult
from app.agent.tools import bill_tool          # 只绑模块，属性延迟到调用时取
from app.models.bill import Bill
from app.models.budget_plan import BudgetPlan

# 复用 bill_tool 里的查询助手。这里刻意不写 `from bill_tool import CATEGORIES, _norm_month`：
# registry 在文件末尾自动导入各工具模块，一旦 bill_tool 先被加载（比如测试直接 import 它），
# 那种写法就会撞上「partially initialized module」循环导入。
def _norm_month(month):
    return bill_tool._norm_month(month)


def _prev_month(month):
    return bill_tool._prev_month(month)


def _months_with_bills(db, user_id):
    return bill_tool._months_with_bills(db, user_id)

# 明显是「按月固定扣」的说法，用来把订阅/水电这类和「打车、午饭」这种高频小额分开
_FIXED_HINT = ("费", "会员", "充值", "宽带", "房租", "订阅", "VIP", "vip", "月租", "套餐", "保险")


def _plan(db, user_id: int, month: str):
    return (db.query(BudgetPlan)
            .filter(BudgetPlan.user_id == user_id, BudgetPlan.month == month).first())


def _month_rows(db, user_id: int, month: str):
    """该月的明细行（分类、金额、日期、来源）。一次查完，几个工具都从这里聚合。"""
    return (db.query(Bill.category, Bill.amount, Bill.bill_date, Bill.source)
            .filter(Bill.user_id == user_id)
            .filter(func.date_format(Bill.bill_date, "%Y-%m") == month)
            .all())


@register_tool(
    name="spending_forecast",
    description=("月末支出预测与超支预警：按本月已花的钱推算到月底会花多少，"
                 "并对照用户设的支出上限判断会不会超、超多少。"
                 "用户问「这个月会不会超」「还能花多少」「照这速度月底多少」时调用。"),
    parameters={
        "month": {"type": "string", "description": "要预测的月份 YYYY-MM，留空默认本月"},
    },
)
def spending_forecast(month: str = "", user_id: int = 0, db=None, **kwargs):
    if db is None:
        return "数据库不可用"
    month = _norm_month(month)
    rows = _month_rows(db, user_id, month)
    if not rows:
        return ("本月（%s）还没有账单记录，无法预测。请如实告诉用户先去记几笔，"
                "或让他说一句话用 add_bill 记账。" % month)

    today = date.today()
    y, m = int(month[:4]), int(month[5:7])
    days_in_month = calendar.monthrange(y, m)[1]
    is_current = (y, m) == (today.year, today.month)
    days_spent = today.day if is_current else days_in_month
    days_spent = max(1, min(days_spent, days_in_month))

    total = round(sum(float(r[1] or 0) for r in rows), 2)
    daily = round(total / days_spent, 2)
    forecast = round(daily * days_in_month, 2)

    plan = _plan(db, user_id, month)
    limit = float(plan.spend_limit or 0) if plan else 0.0

    by_cat = {}
    for cat, amount, _d, _s in rows:
        by_cat[cat or "其他"] = by_cat.get(cat or "其他", 0.0) + float(amount or 0)
    cat_rows = []
    for cat, v in sorted(by_cat.items(), key=lambda x: -x[1]):
        share = v / total if total else 0
        cat_rows.append([cat, "%.2f" % v, "%d%%" % round(share * 100),
                         "%.2f" % (v / days_spent)])

    # 这里只负责把数字算出来摊平给模型，不做算法。本科毕设要的是功能面，
    # 预测精度不是重点 —— 剩下「会不会超、超多少、怎么办」交给大模型根据这些数字判断。
    L = ["[本月支出进度] %s" % month]
    L.append("已花 %.2f 元（%d/%d 天），日均 %.2f 元" % (total, days_spent, days_in_month, daily))
    if is_current:
        L.append("按目前日均推算，月底大约 %.2f 元，还剩 %d 天" % (forecast, days_in_month - days_spent))
        if days_spent <= 5:
            L.append("现在才 %d 号，信息还少，估算很粗，别把数字说死。" % days_spent)
    else:
        L.append("该月已结束，实际支出 %.2f 元" % total)

    if limit > 0:
        gap = round(limit - (forecast if is_current else total), 2)
        L.append("本月支出上限 %.2f 元：%s" % (
            limit, "预计超出 %.2f 元" % -gap if gap < 0 else "还剩 %.2f 元余量" % gap))
        if is_current and gap < 0 and days_in_month > days_spent:
            L.append("要压回上限，后面每天平均只能花 %.2f 元"
                     % max(0.0, (limit - total) / (days_in_month - days_spent)))
    else:
        L.append("用户没设支出上限，所以不要断言「超支」，可以建议他设一个。")

    prev = _prev_month(month)
    prev_total = round(sum(float(r[1] or 0) for r in _month_rows(db, user_id, prev)), 2)
    if prev_total > 0:
        L.append("上月（%s）共 %.2f 元，本月目前%s %.2f 元" % (
            prev, prev_total, "多" if total >= prev_total else "少", abs(total - prev_total)))

    L.append("")
    L.append("请根据上面这些数字，用一两句话告诉用户：照这个花法月底大概多少、"
             "会不会超预算、最需要收着的是哪个分类。只引用这里出现的数字，缺的就说缺。")
    return ToolResult(
        "\n".join(L), [],
        [make_table("%s 支出进度" % month,
                    ["分类", "已花(元)", "占比", "日均(元)"], cat_rows,
                    note="已过 %d/%d 天，日均 %.2f 元" % (days_spent, days_in_month, daily))])


@register_tool(
    name="detect_fixed_spend",
    description=("从账单里找出「每月都在扣的固定支出」和「高频小额」：会员/话费/宽带这类"
                 "容易被忘掉的自动扣费，以及打车/奶茶这类积少成多的开销。"
                 "用户问「有什么我忘掉的扣费」「哪些钱是月月都花的」「哪里最容易省」时调用。"),
    parameters={
        "months": {"type": "integer", "description": "往前看几个月，默认 3"},
    },
)
def detect_fixed_spend(months: int = 3, user_id: int = 0, db=None, **kwargs):
    if db is None:
        return "数据库不可用"
    try:
        span = max(2, min(int(months or 3), 12))
    except (TypeError, ValueError):
        span = 3

    have = _months_with_bills(db, user_id)
    if not have:
        return "这个账号还没有任何账单记录，查不出固定支出。请让用户先记几笔账。"
    window = have[-span:]

    src = func.ifnull(Bill.source, "")
    rows = (db.query(src.label("source"), Bill.category,
                     func.count(func.distinct(func.date_format(Bill.bill_date, "%Y-%m"))).label("m"),
                     func.count(Bill.id).label("cnt"),
                     func.avg(Bill.amount).label("avg"),
                     func.min(Bill.amount).label("mn"),
                     func.max(Bill.amount).label("mx"))
            .filter(Bill.user_id == user_id)
            .filter(func.date_format(Bill.bill_date, "%Y-%m").in_(window))
            .group_by(src, Bill.category).all())

    fixed, frequent = [], []
    for source, cat, m, cnt, avg, mn, mx in rows:
        if not source or m < 2 or cnt < 2:
            continue
        avg, mn, mx = float(avg or 0), float(mn or 0), float(mx or 0)
        if avg < 1:
            continue
        stable = mx <= mn * 1.6 + 1          # 金额基本没变过
        looks_fixed = any(k in source for k in _FIXED_HINT)
        # 说法本身像固定扣费（水电/话费/会员…）→ 2 个月就够；
        # 光靠「金额稳定」要苛刻得多，否则「奶茶 2 笔都 48 元」会被当成订阅。
        if looks_fixed and stable:
            fixed.append((source, cat or "其他", m, cnt, avg, mx))
        elif m >= 3 and cnt <= m + 1 and stable:
            fixed.append((source, cat or "其他", m, cnt, avg, mx))
        elif cnt >= max(3, m * 2):
            frequent.append((source, cat or "其他", m, cnt, avg))

    if not fixed and not frequent:
        return ("%s 这几个月里没有重复出现的支出，说明记账条数还太少"
                "（少于每月两三笔），不要编造订阅项，直接如实告诉用户。" % "、".join(window))

    fixed.sort(key=lambda x: -x[4] * x[3])
    frequent.sort(key=lambda x: -x[4] * x[3])
    L = ["[固定支出与高频小额] 统计区间：%s" % "、".join(window)]

    tables = []
    if fixed:
        L.append("疑似每月固定扣费（一年合计约 %.0f 元）：" % sum(x[4] * x[3] for x in fixed))
        for source, cat, m, cnt, avg, mx in fixed[:8]:
            L.append("- %s（%s）：出现 %d 个月 / %d 笔，单次约 %.2f 元" % (source, cat, m, cnt, avg))
        tables.append(make_table("疑似固定扣费", ["项目", "分类", "出现月数", "笔数", "单次约(元)"],
                                 [[x[0], x[1], str(x[2]), str(x[3]), "%.2f" % x[4]] for x in fixed[:8]]))
    if frequent:
        L.append("")
        L.append("积少成多型（这段时间花得最勤的）：")
        for source, cat, m, cnt, avg in frequent[:8]:
            L.append("- %s（%s）：%d 笔共约 %.2f 元" % (source, cat, cnt, avg * cnt))
        tables.append(make_table("高频小额", ["项目", "分类", "笔数", "合计约(元)"],
                                 [[x[0], x[1], str(x[3]), "%.2f" % (x[4] * x[3])] for x in frequent[:8]]))
    L.append("")
    L.append("说明：这是从用户自己记的账里推断的，没接支付渠道，所以「订阅」只是疑似。"
             "回答时不要说成确定事实，用「看起来每月都在扣」这类措辞。")
    return ToolResult("\n".join(L), [], tables)


@register_tool(
    name="cheaper_alternative",
    description=("平替建议：挑出用户某类消费上花了多少，给出更省的替代方案（打车→地铁、"
                 "外卖→食堂、奶茶→自带等）并算出一年能省多少。"
                 "用户说「这块花得有点多，有别的办法吗」「怎么省」时调用。"),
    parameters={
        "topic": {"type": "string", "description": "消费主题关键词，例如：打车、奶茶、外卖、电影"},
    },
)
def cheaper_alternative(topic: str = "", user_id: int = 0, db=None, **kwargs):
    if db is None:
        return "数据库不可用"
    topic = (topic or "").strip()
    if not topic:
        return "请带上要分析的消费主题（如「打车」「奶茶」），不能空着调用本工具。"

    # 主题也允许直接填分类名
    scope = [Bill.category == topic] if topic in bill_tool.CATEGORIES else [
        func.ifnull(Bill.source, "").like("%%%s%%" % topic)]
    rows = (db.query(Bill.amount, Bill.source, Bill.category, Bill.bill_date)
            .filter(Bill.user_id == user_id)
            .filter(*scope).all())
    if not rows:
        return ("没找到与「%s」相关的记账记录。不要编造金额，"
                "可以请用户换个说法，或先记几笔这类消费。" % topic)

    total = round(sum(float(r[0] or 0) for r in rows), 2)
    cnt = len(rows)
    months = len({str(r[3])[:7] for r in rows if r[3]}) or 1
    per_month = round(total / months, 2)
    yearly = round(per_month * 12, 2)

    tips = _ALTERNATIVES.get(topic) or _match_alias(topic)
    L = ["[平替分析] 主题：%s" % topic]
    L.append("共 %d 笔，合计 %.2f 元；跨 %d 个月，月均 %.2f 元，按此节奏一年约 %.2f 元"
             % (cnt, total, months, per_month, yearly))
    biggest = max(rows, key=lambda r: float(r[0] or 0))
    L.append("单笔最大：%.2f 元（%s）" % (float(biggest[0] or 0), biggest[1] or biggest[2] or ""))

    if not tips:
        L.append("")
        L.append("内置攻略里没有「%s」这个主题的平替方案。只报上面的真实数字，"
                 "替代建议让模型凭常识给，但不得编造具体价格数字。" % topic)
        return ToolResult("\n".join(L), [])

    L.append("")
    L.append("可落地的替代方案（省钱比例是经验估算，回答时说明是估算）：")
    saved_any = 0.0
    trows = []
    for how, rate, note in tips:
        save = round(yearly * rate, 2)
        saved_any = max(saved_any, save)
        L.append("- %s：约省 %.2f 元/年（按 %.0f%% 估）%s" % (how, save, rate * 100, "　" + note if note else ""))
        trows.append([how, "%.0f%%" % (rate * 100), "%.2f" % save, note or "—"])
    L.append("")
    L.append("最省的一条大概能省 %.2f 元/年。" % saved_any)
    return ToolResult("\n".join(L), [],
                      [make_table("「%s」平替方案" % topic, ["替代做法", "可省比例", "约省(元/年)", "说明"], trows)])


# 常见高频消费的替代方案：(做法, 可省比例, 补充说明)
_ALTERNATIVES = {
    "打车": [("改坐地铁/公交", 0.6, "同城区间地铁通常 3-7 元，打车 20-40 元"),
             ("非急用改成共享单车", 0.75, "3 公里内"),
             ("拼车或错开高峰", 0.25, "深夜和雨天溢价最高")],
    "奶茶": [("自己泡茶/冲咖啡带出门", 0.7, "一杯奶茶 15-25 元，自己做 2-3 元"),
             ("用平台券和会员日", 0.35, "蜜雪/瑞幸常有 9.9 元档")],
    "外卖": [("改吃食堂或自己做", 0.5, "同一顿外卖通常贵 8-15 元"),
             ("凑满减而不是单点", 0.2, "注意别为凑单多点"),
             ("避开配送费高峰时段", 0.15, "午高峰配送费上浮")],
    "电影": [("改工作场/会员日票", 0.4, "工作日白天通常半价"),
             ("用银行观影活动", 0.5, "多家银行有 5 折观影")],
    "午餐": [("食堂或自带", 0.45, "在外吃一顿 20-35 元"),
             ("团购套餐", 0.25, "比单点便宜")],
    "咖啡": [("自带杯减 5 元", 0.3, "Manner 等店支持"),
             ("用券后 10 元内", 0.45, "别按原价买")],
    "话费": [("改更便宜的套餐", 0.3, "运营商 App 里可自助变更"),
             ("会员日充值", 0.05, "每月 28 日常有活动")],
    "购物": [("加购物车放 24 小时再决定", 0.3, "冲动消费多数会自动取消"),
             ("先比价再下单", 0.15, "可以用比价功能")],
}

_ALIAS = {"打车费": "打车", "叫车": "打车", "网约车": "打车", "喝咖啡": "咖啡",
          "午饭": "午餐", "早饭": "午餐", "晚饭": "外卖", "点外卖": "外卖",
          "看影": "电影", "电影票": "电影", "喝奶茶": "奶茶", "手机充值": "话费"}


def _match_alias(topic: str):
    for k, v in _ALIAS.items():
        if k in topic or topic in k:
            return _ALTERNATIVES.get(v)
    for cat, tips in _ALTERNATIVES.items():
        if cat in topic or topic in cat:
            return tips
    return None


@register_tool(
    name="monthly_report",
    description=("生成某个月的省钱复盘报告：总支出、日均、最大分类、环比、已省金额、打卡天数、"
                 "最值的几笔，最后给一段可以直接发社区的复盘文字。"
                 "用户说「帮我总结这个月」「月度复盘」时调用。"),
    parameters={
        "month": {"type": "string", "description": "月份 YYYY-MM，留空默认本月"},
    },
)
def monthly_report(month: str = "", user_id: int = 0, db=None, **kwargs):
    if db is None:
        return "数据库不可用"
    month = _norm_month(month)
    rows = _month_rows(db, user_id, month)
    if not rows:
        return "%s 没有账单记录，生成不了复盘。请如实告诉用户换个月份或先记账。" % month

    prev = _prev_month(month)
    prev_rows = _month_rows(db, user_id, prev)
    total = round(sum(float(r[1] or 0) for r in rows), 2)
    prev_total = round(sum(float(r[1] or 0) for r in prev_rows), 2)

    today = date.today()
    y, m = int(month[:4]), int(month[5:7])
    dim = calendar.monthrange(y, m)[1]
    days = today.day if (y, m) == (today.year, today.month) else dim
    days = max(1, min(days, dim))

    by_cat = {}
    for cat, amount, _d, _s in rows:
        by_cat[cat or "其他"] = by_cat.get(cat or "其他", 0.0) + float(amount or 0)
    top_cat, top_val = max(by_cat.items(), key=lambda x: x[1])

    plan = _plan(db, user_id, month)
    saved = float(plan.saved_amount or 0) if plan else 0.0
    target = float(plan.target_amount or 0) if plan else 0.0
    checkin = int(plan.checkin_days or 0) if plan else 0

    big = sorted(rows, key=lambda r: -float(r[1] or 0))[:3]

    L = ["[%s 省钱复盘]" % month]
    L.append("总支出 %.2f 元，日均 %.2f 元，共 %d 笔" % (total, total / days, len(rows)))
    if prev_total:
        delta = round(total - prev_total, 2)
        L.append("环比 %s（%.2f 元）：%s %.2f 元（%+.1f%%）" % (
            prev, prev_total, "多花" if delta >= 0 else "少花", abs(delta),
            delta / prev_total * 100))
    else:
        L.append("上月（%s）没有账单，算不出环比——不要凭空编一个百分比" % prev)
    L.append("花得最多的是「%s」%.2f 元，占 %.0f%%" % (top_cat, top_val, top_val / total * 100))
    if saved or target:
        L.append("本月已省 %.2f 元%s，连续打卡 %d 天" % (
            saved, "（目标 %.2f 元，完成 %.0f%%）" % (target, saved / target * 100) if target else "", checkin))
    else:
        L.append("本月没设省钱目标，也没记录到已省金额")
    L.append("最值的三笔：" + "、".join(
        "%.2f元(%s)" % (float(r[1] or 0), r[3] or r[0] or "") for r in big))
    L.append("")
    L.append("请把上面这些真实数字组织成一段口语化的月度复盘，"
             "结尾给 1-2 条下个月能落地的调整。只引用这里出现的数字，缺的就说缺。")
    return ToolResult("\n".join(L), [],
                      [make_table("%s 分类构成" % month, ["分类", "金额(元)", "占比"],
                                  [[c, "%.2f" % v, "%.0f%%" % (v / total * 100)]
                                   for c, v in sorted(by_cat.items(), key=lambda x: -x[1])])])
