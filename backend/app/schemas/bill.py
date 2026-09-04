
# 账单请求/响应模型
# """""
from pydantic import BaseModel
from datetime import date

class BillCreate(BaseModel):
    amount: float
    category: str = "其他"
    source: str = ""
    bill_date: date

class BillResponse(BaseModel):
    id: int
    amount: float
    category: str
    source: str
    bill_date: date

    class Config:
        from_attributes = True
