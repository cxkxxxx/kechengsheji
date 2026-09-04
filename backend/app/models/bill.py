

from sqlalchemy import Column, Date, DateTime, Float, Integer, String, Text, func
from app.core.database import Base

class Bill(Base):
    __tablename__ = "bills"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, nullable=False)              # 用户 ID
    amount = Column(Float, nullable=False)                 # 金额
    category = Column(String(50))                          # 分类：餐饮/购物/交通/娱乐...
    source = Column(String(100))                           # 消费来源描述
    bill_date = Column(Date)                               # 消费日期
    ocr_raw = Column(Text)                                 # OCR 原始数据（如有）
    created_at = Column(DateTime, server_default=func.now())
