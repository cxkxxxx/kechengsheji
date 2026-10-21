"""账单接口序列化老数据的离线回归测试。

起因：给 bills 补 pay_channel / order_no 两列之后，迁移前就存在的老行在这两列上是 NULL。
`BillResponse` 写的是 `pay_channel: str = ""`，但 Pydantic 的默认值只在字段**缺失**时生效，
字段存在而值为 None 时照样报 "Input should be a valid string" —— 于是 GET /bills 整个 500，
账单页的消费明细和「展开全部」都打不开。库里当时 1019/1281 行都是这种状态。
运行：pytest tests/test_bill_schema.py
"""
from datetime import date

from app.schemas.bill import BillResponse


class _Row:
    """冒充一个 ORM 对象，字段值故意用 None。"""

    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


def _row(**over):
    d = dict(id=1, amount=19.4, category="餐饮", source="午餐",
             pay_channel=None, order_no=None, bill_date=date(2026, 9, 15))
    d.update(over)
    return _Row(**d)


def test_legacy_null_columns_still_serialize():
    r = BillResponse.model_validate(_row())
    assert r.pay_channel == ""
    assert r.order_no == ""


def test_source_and_category_null_become_blank():
    r = BillResponse.model_validate(_row(source=None, category=None))
    assert r.source == "" and r.category == ""


def test_real_values_pass_through_untouched():
    r = BillResponse.model_validate(_row(pay_channel="微信支付", order_no="4200431597535375533164"))
    assert r.pay_channel == "微信支付"
    assert r.order_no == "4200431597535375533164"


def test_response_shape_has_new_fields_for_frontend():
    # 前端列表靠这两个字段显示「· 微信支付」和弹窗里的单号，字段名不能漂
    keys = set(BillResponse.model_fields)
    assert {"pay_channel", "order_no", "source", "category", "bill_date"} <= keys
