

from sqlalchemy import Column, Integer, String, Text, DateTime, func
from app.core.database import Base

class CouponActivity(Base):
    __tablename__ = "coupon_activities"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    title = Column(String(200), nullable=False)            # 活动标题
    content = Column(Text)                                 # 活动详情
    platform = Column(String(50))                          # 平台：银行/外卖/话费...
    deadline = Column(DateTime)                            # 截止时间
    verified = Column(Integer, default=0)                  # 是否已验证有效
    created_at = Column(DateTime, server_default=func.now())
