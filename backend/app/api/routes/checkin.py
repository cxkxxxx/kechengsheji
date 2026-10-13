

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
        # 每日省钱打卡

    month = datetime.now().strftime("%Y-%m")
    plan = db.query(BudgetPlan).filter(
        BudgetPlan.user_id == current_user.id,
        BudgetPlan.month == month,
    ).first()
    if not plan:
        plan = BudgetPlan(user_id=current_user.id, month=month, target_amount=500)
        db.add(plan)
        db.commit()
        db.refresh(plan)

    plan.saved_amount += req.saved_amount
    plan.last_checkin_date = datetime.now()
    plan.checkin_days += 1
    current_user.total_saved += req.saved_amount
    db.commit()
    return success({
        "saved_amount": plan.saved_amount,
        "target_amount": plan.target_amount,
        "checkin_days": plan.checkin_days,
        "progress": round(plan.saved_amount / plan.target_amount * 100, 1) if plan.target_amount > 0 else 0,
    })