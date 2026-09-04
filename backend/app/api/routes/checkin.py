

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import datetime
from pydantic import BaseModel

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.budget_plan import BudgetPlan
from app.utils.response import success

router = APIRouter()

class PlanCreate(BaseModel):
        # 设置省钱目标请求

    target_amount: float    # 月度省钱目标（元）

class CheckinRequest(BaseModel):
        # 打卡请求

    saved_amount: float       # 今天省了多少元
    note: str = ""            # 打卡备注

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
    # plan 为 None 时返回默认值，避免前端访问属性报错
    if not plan:
        return success({
            "month": month,
            "target_amount": 0,
            "saved_amount": 0,
            "checkin_days": 0,
            "last_checkin_date": None,
        })
    return success({
        "month": plan.month,
        "target_amount": plan.target_amount,
        "saved_amount": plan.saved_amount,
        "checkin_days": plan.checkin_days,
        "last_checkin_date": plan.last_checkin_date,
    })

@router.post("/plan")
def set_plan(
    req: PlanCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
        # 设置月度省钱目标

    month = datetime.now().strftime("%Y-%m")
    plan = db.query(BudgetPlan).filter(
        BudgetPlan.user_id == current_user.id,
        BudgetPlan.month == month,
    ).first()
    if not plan:
        plan = BudgetPlan(user_id=current_user.id, month=month, target_amount=req.target_amount)
        db.add(plan)
    else:
        plan.target_amount = req.target_amount
    db.commit()
    return success({"month": month, "target_amount": req.target_amount})

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