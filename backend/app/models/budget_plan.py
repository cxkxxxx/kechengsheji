# 省钱打卡计划表
# ==============================
# 用户设置的月度省钱目标及每日打卡记录
""
from sqlalchemy import Column, Integer, String, Float, DateTime, func
from app.core.database import Base

class BudgetPlan(Base):
    __tablename__ = "budget_plans"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, nullable=False)              # 用户 ID
    month = Column(String(7), nullable=False)              # 月份 "2026-09"
    target_amount = Column(Float, default=0)               # 目标省金额
    saved_amount = Column(Float, default=0)                # 已省金额
    checkin_days = Column(Integer, default=0)              # 连续打卡天数
    last_checkin_date = Column(DateTime)                   # 最近打卡时间
