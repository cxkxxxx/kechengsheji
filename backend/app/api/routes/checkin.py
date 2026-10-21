

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime
from pydantic import BaseModel

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.budget_plan import BudgetPlan
from app.models.bill import Bill
from app.utils.response import success

router = APIRouter()

MAX_LIMIT = 10 ** 8


class PlanCreate(BaseModel):
    # 设置月度目标请求：两种目标都可以设，至少给一个
    target_amount: float = 0    # 月度省钱目标（元）
    spend_limit: float = 0      # 月度支出上限（元）


def _month_spend(db: Session, user_id: int, month: str) -> float:
    return float(db.query(func.sum(Bill.amount)).filter(
        Bill.user_id == user_id,
        func.date_format(Bill.bill_date, "%Y-%m") == month,
    ).scalar() or 0)


def _plan_payload(plan, month: str, spend: float) -> dict:
    target = float(plan.target_amount or 0) if plan else 0
    limit = float(plan.spend_limit or 0) if plan else 0
    saved = float(plan.saved_amount or 0) if plan else 0
    return {
        "month": month,
        "target_amount": target,
        "spend_limit": limit,
        "saved_amount": saved,
        "spend": round(spend, 2),
        "checkin_days": int(plan.checkin_days or 0) if plan else 0,
        "last_checkin_date": plan.last_checkin_date if plan else None,
        # 省钱进度：已省 / 目标
        "save_progress": round(saved / target * 100, 1) if target > 0 else 0,
        # 预算使用率：已花 / 上限，超 100% 表示已爆预算
        "budget_used": round(spend / limit * 100, 1) if limit > 0 else 0,
        "budget_left": round(limit - spend, 2) if limit > 0 else 0,
    }

@router.get("/plan")
def get_plan(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
        # 获取当前月的省钱计划

    month = datetime.now().strftime("%Y-%m")
    plan = db.query(BudgetPlan).filter(
        BudgetPlan.user_id == current_user.id,
        BudgetPlan.month == month,
    ).first()
    # 没有计划也回一份全 0 的结构，前端不用到处判空
    return success(_plan_payload(plan, month, _month_spend(db, current_user.id, month)))

@router.post("/plan")
def set_plan(
    req: PlanCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
        # 设置月度目标：省钱目标 / 支出上限，可以同时设

    for label, v in (("省钱目标", req.target_amount), ("支出上限", req.spend_limit)):
        if v < 0:
            raise HTTPException(400, "%s不能是负数" % label)
        if v > MAX_LIMIT:
            raise HTTPException(400, "%s数值太大" % label)
    target = round(float(req.target_amount or 0), 2)
    limit = round(float(req.spend_limit or 0), 2)
    if target <= 0 and limit <= 0:
        raise HTTPException(400, "至少设一个目标：本月省多少，或本月最多花多少")

    month = datetime.now().strftime("%Y-%m")
    plan = db.query(BudgetPlan).filter(
        BudgetPlan.user_id == current_user.id,
        BudgetPlan.month == month,
    ).first()
    if not plan:
        plan = BudgetPlan(user_id=current_user.id, month=month)
        db.add(plan)
    plan.target_amount = target
    plan.spend_limit = limit
    db.commit()
    return success(_plan_payload(plan, month, _month_spend(db, current_user.id, month)), "目标已保存")

class CheckinRequest(BaseModel):
        # 打卡请求

    saved_amount: float       # 今天省了多少元
    note: str = ""            # 打卡备注

@router.post("/do")
def do_checkin(
    req: CheckinRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """每日省钱打卡。同一天重复提交按「改当天这条」处理，不会累计两次。

    原来这里是 `plan.checkin_days += 1` / `plan.saved_amount += 金额`，
    前端按钮没有任何防重，连点两次就把天数和金额都翻倍了。
    现在明细写 checkins 表（一人一天一条），budget_plans 上的累计值由明细重算。
    """
    from datetime import date as _date
    from app.models.checkin import Checkin

    if req.saved_amount < 0:
        raise HTTPException(400, "省钱金额不能是负数")
    if req.saved_amount > MAX_LIMIT:
        raise HTTPException(400, "省钱金额数值太大")

    today = _date.today()
    month = today.strftime("%Y-%m")
    plan = db.query(BudgetPlan).filter(
        BudgetPlan.user_id == current_user.id,
        BudgetPlan.month == month,
    ).first()
    if not plan:
        plan = BudgetPlan(user_id=current_user.id, month=month, target_amount=500)
        db.add(plan)
        db.commit()
        db.refresh(plan)

    before_total = float(plan.saved_amount or 0)
    row = db.query(Checkin).filter(
        Checkin.user_id == current_user.id, Checkin.day == today).first()
    if row:
        row.saved_amount = round(float(req.saved_amount), 2)
        row.note = (req.note or "")[:120]
        repeated = True
    else:
        db.add(Checkin(user_id=current_user.id, day=today,
                       saved_amount=round(float(req.saved_amount), 2),
                       note=(req.note or "")[:120]))
        repeated = False
    db.commit()

    # 用明细重算累计，避免 += 带来的重复累加和漂移
    total, days = db.query(func.coalesce(func.sum(Checkin.saved_amount), 0), func.count(Checkin.id)) \
        .filter(Checkin.user_id == current_user.id,
                func.date_format(Checkin.day, "%Y-%m") == month).first()
    plan.saved_amount = round(float(total or 0), 2)
    plan.checkin_days = int(days or 0)
    plan.last_checkin_date = datetime.now()
    # 用户总节省跟着本次增量走，而不是再加一遍
    delta = plan.saved_amount - before_total
    current_user.total_saved = max(0.0, round(float(current_user.total_saved or 0) + delta, 2))
    db.commit()

    return success({
        "saved_amount": plan.saved_amount,
        "target_amount": plan.target_amount,
        "checkin_days": plan.checkin_days,
        "progress": round(plan.saved_amount / plan.target_amount * 100, 1) if plan.target_amount > 0 else 0,
        "repeated": repeated,
        "today_saved": round(float(req.saved_amount), 2),
    }, "今天已经打过卡了，已按你新填的金额更新" if repeated else "打卡成功")


@router.get("/month")
def month_checkins(
    month: str = "",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """某月的打卡明细，给账单页的「打卡日历」用。"""
    from datetime import date as _date
    from app.models.checkin import Checkin
    month = (month or "").strip() or _date.today().strftime("%Y-%m")
    rows = (db.query(Checkin).filter(
            Checkin.user_id == current_user.id,
            func.date_format(Checkin.day, "%Y-%m") == month)
            .order_by(Checkin.day).all())
    days = [{"day": r.day.day, "saved_amount": round(float(r.saved_amount or 0), 2),
             "note": r.note or ""} for r in rows]
    return success({
        "month": month,
        "days": days,
        "count": len(days),
        "total": round(sum(d["saved_amount"] for d in days), 2),
        "today": _date.today().day if _date.today().strftime("%Y-%m") == month else None,
        "checked_today": any(d["day"] == _date.today().day
                             for d in days) if _date.today().strftime("%Y-%m") == month else False,
    })