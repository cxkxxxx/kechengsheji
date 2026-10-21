"""演示账单生成器：造出**有真实结构**的家庭支出，而不是均匀随机数。

## 为什么要专门造结构

最初的生成器是「每月 26~34 笔、金额从固定区间独立均匀抽取、日期在全月均匀撒」。
用它跑预测算法对比回测，结果是：

    历史月均 15.1%   线性外推 37.2%   完成度曲线 50.8%

也就是**最朴素的方法就是最优解**，任何算法都不可能赢。原因是这种数据在统计上
每月同分布、月内无形状，「本月已花多少」不含任何额外信息。算法章节会因此空掉。

真实家庭支出不是这样的，所以这里把三条真实结构造进来：

1. **月内形状** —— 房租/水电/宽带/话费集中在月初 1~8 号；发薪日（15 号）之后
   餐饮娱乐明显上浮；周末外出消费概率更高。→ 让「月内完成度曲线」有规律可学。
2. **月度漂移** —— 每个用户有一条缓慢的消费增长趋势，再叠加大促月份系数
   （618 / 双11 / 春节）。→ 让「历史月均」开始失准，趋势类方法才有存在价值。
3. **个体差异** —— 有人月花 1800、有人 6500，且消费结构分吃货型/购物型/通勤型。
   → 这是聚类画像（K-Means）的前提；同分布的人群聚出来只有噪声。

同一 user_id 每次生成结果一致（用种子随机），演示可以重复。
"""
import random
from datetime import date, timedelta

CATEGORIES = ["餐饮", "购物", "交通", "生活", "娱乐", "医疗", "其他"]

# 月初固定支出：(用途·商户, 分类, 金额区间, 落在几号到几号, 常用渠道, 是否随消费水平缩放)
# 金额刻意压到「合计约占月支出 35~45%」：房租对独居年轻人确实是最大单项，
# 但如果让它占到全月七八成，第 2、3 旬就几乎没钱可花，日分布会假得不能用。
#
# 最后一项 scale=True 的（房租、水电）按用户月基准缩放：月花 1661 的人不该和
# 月花 8000 的人交一样多的房租，否则低预算用户的固定项就吃掉了整月，
# 实测会出现「第 1 旬占 92%」这种退化分布。话费/会员/单车是标价商品，不缩放。
_FIXED_ITEMS = [
    ("房租分摊·自如", "生活", (780, 1380), (1, 3), ["支付宝", "微信支付"], True),
    ("水电燃气费", "生活", (88, 248), (4, 8), ["支付宝", "微信支付"], True),
    ("宽带月租·中国电信", "生活", (58, 79), (2, 6), ["支付宝"], False),
    ("话费充值·中国移动", "生活", (30, 98), (8, 14), ["微信支付", "支付宝"], False),
    ("视频会员自动续费", "生活", (15, 25), (10, 18), ["微信支付", "支付宝"], False),
    ("共享单车月卡", "交通", (12, 18), (1, 5), ["微信支付"], False),
]

# 日常浮动支出：(用途·商户, 分类, 金额区间, 常用渠道, 权重)
# 权重决定这类消费出现的相对频次；金额区间决定单笔大小
_ROUTINE_ITEMS = [
    ("早餐·老面包子铺", "餐饮", (5, 14), ["微信支付"], 1.4),
    ("午餐·公司食堂", "餐饮", (12, 26), ["微信支付", "支付宝"], 1.6),
    ("晚餐·外卖", "餐饮", (18, 42), ["美团支付", "微信支付"], 1.2),
    ("奶茶·蜜雪冰城", "餐饮", (6, 18), ["微信支付"], 0.7),
    ("咖啡·瑞幸", "餐饮", (9, 20), ["支付宝"], 0.7),
    ("聚餐·火锅", "餐饮", (88, 226), ["微信支付", "支付宝"], 0.28),
    ("超市日用品·永辉超市", "购物", (28, 128), ["微信支付", "云闪付"], 0.8),
    ("衣服·淘宝", "购物", (79, 399), ["支付宝"], 0.45),
    ("数码配件·京东", "购物", (25, 259), ["京东支付", "微信支付"], 0.32),
    ("日用品·拼多多", "购物", (12, 89), ["微信支付"], 0.5),
    ("地铁通勤", "交通", (3, 9), ["微信支付", "支付宝"], 1.8),
    ("打车·滴滴出行", "交通", (11, 46), ["微信支付", "支付宝"], 0.65),
    ("公交", "交通", (1, 4), ["微信支付"], 0.8),
    ("电影票", "娱乐", (35, 68), ["淘票票", "微信支付"], 0.25),
    ("游戏充值", "娱乐", (6, 128), ["微信支付", "支付宝"], 0.22),
    ("药品·大药房", "医疗", (18, 96), ["微信支付", "支付宝"], 0.18),
    ("门诊挂号", "医疗", (10, 45), ["支付宝", "微信支付"], 0.08),
    ("生日礼物", "其他", (45, 220), ["微信支付", "支付宝"], 0.1),
]

# 三种人群原型：分类 → 该分类占总浮动的相对权重
_ARCHETYPES = {
    "吃货型": {"餐饮": 3.0, "购物": 0.7, "交通": 0.9, "生活": 0.6, "娱乐": 1.1, "医疗": 0.3, "其他": 0.6},
    "购物型": {"餐饮": 1.1, "购物": 3.0, "交通": 0.8, "生活": 0.9, "娱乐": 0.9, "医疗": 0.3, "其他": 1.0},
    "通勤型": {"餐饮": 1.2, "购物": 0.8, "交通": 3.0, "生活": 0.8, "娱乐": 0.7, "医疗": 0.4, "其他": 0.7},
}
_ARCH_KEYS = list(_ARCHETYPES)

# 大促/节假日系数：让月与月之间不再同分布
_SEASON = {1: 1.06, 2: 1.18, 6: 1.22, 8: 1.04, 11: 1.28, 12: 1.10}


def profile_for(user_id: int) -> dict:
    """由 user_id 派生出稳定的用户画像：消费水平、人群原型、月度增长率。"""
    rng = random.Random(1000 + int(user_id) * 7919)
    # 基准下限定在 2400：再低的话月初固定项（房租+水电+宽带+话费）就吃掉整月大半，
    # 日常消费没空间，实测会退化成「第 1 旬占 70~78%」这种不像人的分布。
    base = round(rng.uniform(2400, 7200), 0)
    arch = _ARCH_KEYS[int(user_id) % len(_ARCH_KEYS)]
    # 增长率可正可负：有人消费升级，有人开始省钱
    growth = round(rng.uniform(-0.025, 0.045), 4)
    return {"user_id": int(user_id), "monthly_base": base, "archetype": arch,
            "growth": growth, "weights": _ARCHETYPES[arch]}


def _month_index(ym: str) -> int:
    return int(ym[:4]) * 12 + int(ym[5:7])


def month_target(user_id: int, ym: str) -> float:
    """该用户该月「计划」花多少：基准 × (1+增长率)^月序 × 季节系数。

    注意这只是**计划值**，不含月度冲击。真实月份会有 ±20% 上下的随机波动
    （生病、随份子、短途旅游），所以真正落到账单上的总额要用 month_actual_target。
    早先漏了这一项，导致每月总额几乎精确等于计划值，回测里「历史月均」跑出 3.7% MAPE
    —— 那是把答案写进了数据，不是算法强。
    """
    p = profile_for(user_id)
    idx = _month_index(ym) - _month_index("2026-01")
    return round(p["monthly_base"] * ((1 + p["growth"]) ** max(0, idx))
                 * _SEASON.get(int(ym[5:7]), 1.0), 2)


def month_actual_target(user_id: int, ym: str) -> float:
    """计划值再叠一个按 (用户, 月份) 确定的随机冲击，模拟真实月度波动。

    用 seed 保证同一用户同一月每次生成结果一致，演示可重复。
    0.82~1.24 的区间偏正一点，对应「多数人某个月会突然多花一笔」。
    """
    rng = random.Random(int(user_id) * 977 + _month_index(ym) * 31)
    return round(month_target(user_id, ym) * rng.uniform(0.82, 1.24), 2)


def _day_weight(d: date) -> float:
    """月内形状：周末更高，发薪日后更高。"""
    w = 1.0
    if d.weekday() >= 5:
        w *= 1.6                      # 周六周日外出消费明显多
    if 15 <= d.day <= 20:
        w *= 1.35                     # 发薪日效应
    elif d.day <= 5:
        w *= 0.85                     # 月初刚交完房租，日常收紧
    return w


def generate_month(db, user_id: int, ym: str, today: date = None) -> dict:
    """生成该用户该月的账单 dict 列表（不入库，交给调用方决定怎么插）。

    月初固定项先扣掉，剩下的预算按日权重撒成日常浮动消费。
    """
    today = today or date.today()
    import calendar
    y, m = int(ym[:4]), int(ym[5:7])
    dim = calendar.monthrange(y, m)[1]
    last_day = dim if date(y, m, dim) < today else today.day
    if last_day < 1:
        return {"rows": [], "target": 0.0, "fixed": 0.0}

    rng = random.Random(int(user_id) * 131 + _month_index(ym))
    p = profile_for(user_id)
    target = month_actual_target(user_id, ym)
    # 房租/水电随消费水平缩放，夹在 0.45~1.6 倍之间：
    # 低预算用户不至于交不起房租，高预算用户也不至于房租小得离谱。
    fscale = max(0.45, min(1.6, p["monthly_base"] / 3600.0))

    rows, fixed_total = [], 0.0
    # 1) 月初固定支出
    for label, cat, (lo, hi), (d1, d2), chans, scales in _FIXED_ITEMS:
        dom = rng.randint(d1, min(d2, last_day))
        k = fscale if scales else 1.0
        amt = round(rng.uniform(lo, hi) * k, 2)
        fixed_total += amt
        rows.append(_row(user_id, cat, label, amt, date(y, m, dom), rng))

    # 2) 日常浮动：把剩余预算撒到每一天，按日权重决定「这天花多少」和「分几笔」
    budget = max(120.0, target - fixed_total)
    days = [date(y, m, d) for d in range(1, last_day + 1)]
    weights = [_day_weight(d) for d in days]
    tw = sum(weights) or 1.0
    # 笔数随预算规模走：月花 1800 的人和月花 6500 的人不该都是 28 笔。
    # 之前写死 20~34 笔，导致高预算用户怎么抽都凑不到目标（scale 被钳制挡掉，
    # 结果「目标 5436 只造出 1794」）。
    n_txn = max(18, min(46, int(budget / 95)))
    routine = []
    for _ in range(n_txn):
        pick = rng.random() * tw
        acc, day = 0.0, days[-1]
        for d, w in zip(days, weights):
            acc += w
            if pick <= acc:
                day = d
                break
        label, cat, (lo, hi), chans, cw = _pick_item(rng, p)
        routine.append([label, cat, round(rng.uniform(lo, hi) * rng.uniform(0.72, 1.28), 2), day])
    # 按预算整体缩放日常项，让月总额真的贴住 month_target。
    # 房租水电是定额不参与缩放，否则「这个月房租多少」就随预算变了，不合常理。
    rsum = sum(r[2] for r in routine) or 1.0
    k = budget / rsum
    for label, cat, amt, day in routine:
        rows.append(_row(user_id, cat, label, amt * k, day, rng))

    return {"rows": rows, "target": target, "fixed": round(fixed_total, 2)}


def _pick_item(rng, profile):
    """按人群原型加权抽一类消费：吃货型更容易抽到餐饮。"""
    items, ws = [], []
    for it in _ROUTINE_ITEMS:
        items.append(it)
        ws.append(it[4] * profile["weights"].get(it[1], 1.0))
    return rng.choices(items, weights=ws, k=1)[0]


_ORDER_PREFIX = {"微信支付": "4200", "支付宝": "2200", "云闪付": "1300",
                 "京东支付": "7100", "美团支付": "8300", "淘票票": "3100"}

# 造数据用的渠道池，按真实使用频率加权（微信/支付宝占绝大多数）
_CHANNEL_POOL = ["微信支付"] * 5 + ["支付宝"] * 4 + ["云闪付", "京东支付", "美团支付"]


def make_order_no(channel: str, d: date, rng) -> str:
    """按各家真实单号的样子拼一个：微信 4200 开头，支付宝以交易日期开头。"""
    prefix = _ORDER_PREFIX.get(channel, "4200")
    digits = "".join(rng.choice("0123456789") for _ in range(18))
    if channel == "支付宝":
        return "%04d%02d%02d%s" % (d.year, d.month, d.day, digits)
    return prefix + digits[4:]


def _row(user_id, cat, label, amt, d, rng) -> dict:
    # 渠道列表在这里自己存一份：bill_tool 那边也有个 _CHANNELS，但那是「归一模型吐出的
    # 说法」用的映射表，而这里是「造数据」。让 demo_bills 反向 import 路由模块会绕成环。
    ch = rng.choice(_CHANNEL_POOL)
    return {"user_id": user_id, "category": cat, "source": label,
            "amount": round(amt, 2), "bill_date": d, "pay_channel": ch,
            "order_no": make_order_no(ch, d, rng) if rng.random() < 0.62 else ""}
