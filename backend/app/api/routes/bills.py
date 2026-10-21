

from fastapi import APIRouter, Depends, HTTPException
from datetime import date, datetime
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.bill import Bill
from app.schemas.bill import BillCreate, BillUpdate, BillResponse
from app.utils.response import success
from app.agent.llm import call_llm_simple

router = APIRouter()

# 演示账单按分类给贴近真实的价格区间。以前一律 uniform(8, 300)，会生成
# 「奶茶 280 块」「地铁 9 块」这种假数据，把分类占比和 AI 的账单分析一起带跑。
_DEMO_CATS = {
    "餐饮": (["早餐", "午餐", "晚餐", "外卖", "奶茶", "咖啡", "食堂"], (6, 88)),
    "购物": (["淘宝", "京东", "拼多多", "超市日用品", "衣服"], (25, 420)),
    "交通": (["地铁", "公交", "打车", "共享单车"], (2, 46)),
    "生活": (["水电费", "话费", "日用品", "宽带"], (15, 260)),
    "娱乐": (["电影票", "游戏充值", "KTV", "演出"], (35, 210)),
    "医疗": (["药品", "挂号", "体检"], (20, 320)),
    "其他": (["礼物", "宠物", "杂项"], (20, 220)),
}


def _month_str(y: int, m: int) -> str:
    return "%04d-%02d" % (y, m)


def _back_months(anchor: str, count: int) -> list:
    """从 anchor(YYYY-MM) 往前取 count 个月，返回升序的 YYYY-MM 列表。"""
    y, m = int(anchor[:4]), int(anchor[5:7])
    out = []
    for _ in range(max(1, min(int(count), 24))):
        out.append(_month_str(y, m))
        m -= 1
        if m < 1:
            m, y = 12, y - 1
    return out[::-1]


def _month_bounds(ym: str) -> tuple:
    """该月的 (第一天, 最后一天)。用 calendar 而不是写死 30/31，闰年 2 月才不会错。"""
    import calendar
    y, m = int(ym[:4]), int(ym[5:7])
    return date(y, m, 1), date(y, m, calendar.monthrange(y, m)[1])

@router.get("")
def get_bills(
    month: str = "",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # # 获取用户账单列表（可按月份筛选，格式 2026-09）
    query = db.query(Bill).filter(Bill.user_id == current_user.id)
    if month:
        query = query.filter(func.date_format(Bill.bill_date, "%Y-%m") == month)
    items = query.order_by(Bill.bill_date.desc()).all()
    return success([BillResponse.model_validate(b) for b in items])

@router.post("")
def create_bill(
    bill_data: BillCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
        # 手动记一笔消费

    bill = Bill(
        user_id=current_user.id,
        amount=bill_data.amount,
        category=bill_data.category,
        source=bill_data.source,
        bill_date=bill_data.bill_date,
    )
    db.add(bill)
    db.commit()
    db.refresh(bill)
    return success(BillResponse.model_validate(bill))

@router.get("/months")
def get_months(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 该用户有账单的月份（新→旧），供前端月份切换器使用
    rows = (db.query(func.date_format(Bill.bill_date, "%Y-%m").label("m"),
                     func.count(Bill.id), func.sum(Bill.amount))
            .filter(Bill.user_id == current_user.id)
            .group_by("m").order_by(func.date_format(Bill.bill_date, "%Y-%m").desc()).all())
    return success([{"month": r[0], "count": r[1], "total": round(float(r[2] or 0), 2)} for r in rows if r[0]])


@router.put("/{bill_id}")
def update_bill(
    bill_id: int,
    bill_data: BillUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 改一笔账单（只允许改自己的）
    bill = db.query(Bill).filter(Bill.id == bill_id, Bill.user_id == current_user.id).first()
    if not bill:
        raise HTTPException(status_code=404, detail="账单不存在")
    for field, value in bill_data.model_dump(exclude_unset=True).items():
        setattr(bill, field, value)
    db.commit()
    db.refresh(bill)
    return success(BillResponse.model_validate(bill))


@router.delete("/{bill_id}")
def delete_bill(
    bill_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 删一笔账单（只允许删自己的）
    bill = db.query(Bill).filter(Bill.id == bill_id, Bill.user_id == current_user.id).first()
    if not bill:
        raise HTTPException(status_code=404, detail="账单不存在")
    db.delete(bill)
    db.commit()
    return success({"deleted": bill_id})


@router.get("/summary")
def get_summary(
    month: str = "",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # # 账单月度汇总（按分类统计总金额）
    query = db.query(Bill).filter(Bill.user_id == current_user.id)
    if month:
        query = query.filter(func.date_format(Bill.bill_date, "%Y-%m") == month)
    bills = query.all()
    # 按分类汇总
    summary = {}
    total = 0
    for b in bills:
        summary[b.category] = summary.get(b.category, 0) + b.amount
        total += b.amount
    return success({"categories": summary, "total": total, "count": len(bills)})



@router.post("/seed-demo")
def seed_demo(
    month: str = "",
    months: int = 4,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """按月份导入演示账单。

    month  锚定月 YYYY-MM，默认**本月**。默认锚在本月是有原因的：以前写死 7/8/9 三个月，
           等时间走到 10 月，账单页默认视图和「分析一下我这月账单」全是空的。
    months 从锚定月往前一共灌几个月，默认 4，保证环比和趋势都有数据可比。

    只删掉将要写入的那几个月。原来这里无条件 delete 当前用户全部账单，
    用户自己记的账会被这个「导入演示」按钮一键抹掉。
    """
    import random
    import re
    import calendar

    anchor = (month or "").strip()
    if not re.match(r"^\d{4}-(0[1-9]|1[0-2])$", anchor):
        anchor = date.today().strftime("%Y-%m")
    try:
        count = int(months)
    except (TypeError, ValueError):
        count = 4

    targets = _back_months(anchor, count)
    today = date.today()

    deleted = 0
    for ym in targets:
        start, last = _month_bounds(ym)
        deleted += db.query(Bill).filter(Bill.user_id == current_user.id,
                                         Bill.bill_date >= start,
                                         Bill.bill_date <= last).delete(synchronize_session=False)

    cnt = 0
    for ym in targets:
        start, last = _month_bounds(ym)
        # 本月不能灌到还没发生的日期，否则账单里出现「未来的消费」，环比和打卡都会怪
        hi_day = min(last.day, today.day) if (start.year, start.month) == (today.year, today.month) else last.day
        if hi_day < 1:
            continue
        for _ in range(random.randint(26, 34)):
            cat = random.choice(list(_DEMO_CATS))
            names, (lo, hi) = _DEMO_CATS[cat]
            db.add(Bill(user_id=current_user.id,
                        amount=round(random.uniform(lo, hi), 1),
                        category=cat, source=random.choice(names),
                        bill_date=date(start.year, start.month, random.randint(1, hi_day))))
            cnt += 1
    db.commit()
    return success({"imported": cnt, "cleared": deleted, "months": targets,
                    "tip": "已导入 %s 共 %d 条演示账单" % ("、".join(targets), cnt)})


@router.get("/analysis")
def ai_analysis(
    month: str = "",
    need_advice: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # AI 账单可视化分析接口
    # 返回：分类占比列表 + 上月对比 + LLM 生成的省线建议
    from sqlalchemy import func as _f

    if not month:
        month = datetime.now().strftime("%Y-%m")

    # 解析月份，用于上月
    try:
        y, m = map(int, month.split("-"))
    except Exception:
        y, m = datetime.now().year, datetime.now().month
    # 上月
    prev_month = (y - 1, 12) if m == 1 else (y, m - 1)
    prev_str = "%04d-%02d" % prev_month

    # 本月按分类统计
    rows = (db.query(Bill.category, _f.sum(Bill.amount).label("total"), _f.count(Bill.id).label("cnt"))
        .filter(Bill.user_id == current_user.id)
        .filter(_f.date_format(Bill.bill_date, "%Y-%m") == month)
        .group_by(Bill.category).all())

    total = sum(float(r.total or 0) for r in rows)
    # 日均按"有消费的天数"算，摊到整月会让低频用户看起来特别省
    days_with_bills = (db.query(_f.count(_f.distinct(_f.date(Bill.bill_date))))
        .filter(Bill.user_id == current_user.id)
        .filter(_f.date_format(Bill.bill_date, "%Y-%m") == month)
        .scalar()) or 1
    categories = [{
        "name": r[0] or "其他",
        "amount": round(float(r[1] or 0), 2),
        "pct": round(float(r[1] or 0) / total * 100, 1) if total > 0 else 0,
        "count": r[2],
    } for r in rows]
    categories.sort(key=lambda x: x["amount"], reverse=True)

    # 上月总额
    prev_total = (db.query(_f.sum(Bill.amount))
        .filter(Bill.user_id == current_user.id)
        .filter(_f.date_format(Bill.bill_date, "%Y-%m") == prev_str)
        .scalar()) or 0
    prev_total = float(prev_total)

    # 环比变化
    diff = round(total - prev_total, 2)
    diff_pct = round((total - prev_total) / prev_total * 100, 1) if prev_total > 0 else None

    # AI 生成建议：仅当 need_advice 为 True 时才调 LLM，避免浪费 token
    ai_advice = ""
    if categories and need_advice:
        prompt = "以下是我的本月消费账单分类汇总：\n" + "\n".join(
            f"- {c['name']}: {c['amount']}元({c['pct']}%)" for c in categories
        )
        prompt += "\n上月总支出: {:.2f}元, 本月总支出: {:.2f}元".format(prev_total, total)
        prompt += "\n请用3-5句话给出一条贴心、幽默又实用的省钱建议，直接输出建议正文。"
        try:
            ai_advice = call_llm_simple(prompt, "你是一个接地气的省钱生活达人，语气亲切带点幽默。")
        except Exception:
            ai_advice = max(categories, key=lambda x: x["amount"]).get("name", "") + \
                " 占比最高，建议下月适当控制支出，每周复盘一次账单计划哦~"

    return success({
        "month": month,
        "total": round(total, 2),
        "count": sum(r[2] for r in rows),
        "daily_avg": round(total / max(days_with_bills, 1), 2),
        "days": days_with_bills,
        "categories": categories,
        "prev_month": prev_str,
        "prev_total": round(prev_total, 2),
        "diff": diff,
        "diff_pct": diff_pct,
        "ai_advice": ai_advice,
    })