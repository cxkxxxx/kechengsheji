
# 账单请求/响应模型
# """""
from pydantic import BaseModel, field_validator
from datetime import date


def _blank_if_none(v):
    """迁移前就存在的老行，新列在库里是 NULL。

    Pydantic 的 `str = ""` 只在字段**缺失**时兜底，字段存在但值为 None 时照样报
    「Input should be a valid string」，于是 GET /bills 整个 500、账单页打不开。
    """
    return "" if v is None else v

class BillCreate(BaseModel):
    amount: float
    category: str = "其他"
    source: str = ""
    pay_channel: str = ""
    order_no: str = ""
    bill_date: date

class BillUpdate(BaseModel):
    amount: float | None = None
    category: str | None = None
    source: str | None = None
    pay_channel: str | None = None
    order_no: str | None = None
    bill_date: date | None = None

class BillResponse(BaseModel):
    id: int
    amount: float
    category: str
    source: str
    pay_channel: str = ""
    order_no: str = ""
    bill_date: date

    _clean_channel = field_validator("pay_channel", "order_no", "source", "category",
                                     mode="before")(_blank_if_none)

    class Config:
        from_attributes = True
