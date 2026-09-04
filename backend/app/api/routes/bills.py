

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.bill import Bill
from app.schemas.bill import BillCreate, BillResponse
from app.utils.response import success

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
