
# 账单请求/响应模型
# """""
from pydantic import BaseModel
from datetime import date

class BillCreate(BaseModel):
    amount: float
    category: str = "其他"
    source: str = ""
    bill_date: date

class BillUpdate(BaseModel):
    amount: float | None = None
    category: str | None = None
    source: str | None = None
    bill_date: date | None = None

class BillResponse(BaseModel):
    id: int
    amount: float
    category: str
    source: str
    bill_date: date

    class Config:
        from_attributes = True
