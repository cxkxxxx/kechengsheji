

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
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 给当前用户导入演示账单数据（7/8/9 三个月），用于展示
    import random
    from datetime import date as _date
    cats = ["餐饮", "购物", "交通", "生活", "娱乐", "医疗", "其他"]
    sources = {
        "餐饮": ["早餐", "午餐", "晚餐", "奶茶", "外卖", "火锅"],
        "购物": ["淘宝", "京东", "拼多多", "超市日用品"],
        "交通": ["地铁", "公交", "打车", "共享单车"],
        "生活": ["水电费", "话费", "房租分摊", "日用品"],
        "娱乐": ["电影票", "游戏充值", "KTV", "演唱会"],
        "医疗": ["药品", "挂号", "体检"],
        "其他": ["礼物", "宠物", "杂项"],
    }
    # 先清掉当前用户已有账单，避免重复
    db.query(Bill).filter(Bill.user_id == current_user.id).delete()
    cnt = 0
    for m, maxday in [(7, 31), (8, 31), (9, 18)]:
        for _ in range(30):
            cat = random.choice(cats)
            day = random.randint(1, maxday)
            db.add(Bill(user_id=current_user.id, amount=round(random.uniform(8, 300), 1),
                        category=cat, source=random.choice(sources[cat]),
                        bill_date=_date(2026, m, day)))
            cnt += 1
    db.commit()
    return success({"imported": cnt, "tip": "已导入 " + str(cnt) + " 条演示账单"})


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