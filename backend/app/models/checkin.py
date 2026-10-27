from sqlalchemy import Column, Date, DateTime, Float, Integer, String, func

from app.core.database import Base


class Checkin(Base):
    """省钱记录明细（省钱打卡是它的来源之一）。

    早期一行一天、重复打卡覆盖当天那条，够「每日打卡」用；
    但省钱闭环要的是「按攻略/AI 方案执行后记一笔」，一天可能有多笔、
    还要能追溯到来源（哪条攻略/哪个帖子/哪次 AI 方案），所以：
    - 去掉 (user_id, day) 唯一约束，一天可以多笔；
    - 加 source（打卡/攻略/社区经验/AI方案）、ref_type/ref_id（关联内容）。
    budget_plans.saved_amount 仍由本表明细按月重算，口径不变：这里存的
    全部是用户自己确认的实际节省，预计值（攻略/工具里算的「约省」）不进这张表。
    """
    __tablename__ = "checkins"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    day = Column(Date, nullable=False, index=True)       # 记录日期，一天可以多笔
    saved_amount = Column(Float, default=0)              # 这笔实际省了多少元
    note = Column(String(120), default="")               # 备注（省在哪了）
    source = Column(String(20), default="打卡", server_default="打卡")   # 打卡/攻略/社区经验/AI方案
    ref_type = Column(String(20), default="", server_default="")        # 关联内容类型：article/post
    ref_id = Column(Integer, nullable=True)              # 关联内容 id
    created_at = Column(DateTime, server_default=func.now())
