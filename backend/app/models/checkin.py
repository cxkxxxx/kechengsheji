from sqlalchemy import Column, Date, DateTime, Float, Integer, String, UniqueConstraint, func

from app.core.database import Base


class Checkin(Base):
    """每日省钱打卡明细，一行一天。

    为什么不能继续只用 budget_plans：那张表只有 checkin_days（累计天数）和
    last_checkin_date（最后一次时间），**没有每天记录了什么**。所以「本月打卡日历」
    这种要按天显示的功能光靠它做不出来。而且原来的 /checkin/do 是
    `plan.checkin_days += 1`、`plan.saved_amount += 金额`，同一天连点两次就会
    把天数和金额都翻倍 —— 没有幂等保护。

    现在明细放这张表，budget_plans 上的累计值改成由明细重算，重复打卡只会改当天那条。
    """
    __tablename__ = "checkins"
    __table_args__ = (UniqueConstraint("user_id", "day", name="uq_checkin_user_day"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    day = Column(Date, nullable=False)                   # 打卡日期，一人一天最多一条
    saved_amount = Column(Float, default=0)              # 当天省了多少元
    note = Column(String(120), default="")               # 当天备注
    created_at = Column(DateTime, server_default=func.now())
