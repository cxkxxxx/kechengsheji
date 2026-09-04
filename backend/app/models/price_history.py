

from sqlalchemy import Column, Integer, String, Float, DateTime, func
from app.core.database import Base

class PriceHistory(Base):
    __tablename__ = "price_histories"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    product_name = Column(String(200), nullable=False)     # 商品名称
    price = Column(Float, nullable=False)                  # 价格
    platform = Column(String(50))                          # 平台：京东/拼多多/淘宝
    url = Column(String(500))                              # 商品链接
    recorded_at = Column(DateTime, server_default=func.now())
