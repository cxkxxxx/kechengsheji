"""记账金额解析的离线回归测试。

起因：微信/支付宝的账单截图里支出显示成 `-295.00`，模型忠实照抄负号，
而 `_as_amount` 要求 `0 < f`，于是拍照记账「一条都没记上：第 1 条金额无效（-295）」。
运行：pytest tests/test_add_bill.py
"""
from app.agent.tools.bill_tool import _as_amount


def test_negative_amount_from_payment_screenshot_becomes_positive():
    # 截图里的 -295.00 是「支出了 295」，不是无效值
    assert _as_amount(-295) == 295.0
    assert _as_amount("-295.00") == 295.0
    assert _as_amount(-17.5) == 17.5


def test_normal_positive_amount_unchanged():
    assert _as_amount(32) == 32.0
    assert _as_amount("18元") == 18.0
    assert _as_amount("¥295") == 295.0
    assert _as_amount("1,299") == 1299.0      # 千分位也要能吃下


def test_zero_and_garbage_still_rejected():
    assert _as_amount(0) is None
    assert _as_amount("0") is None
    assert _as_amount("") is None
    assert _as_amount(None) is None
    assert _as_amount("看不清") is None
    assert _as_amount(10 ** 8) is None        # 离谱数量级仍然拦掉
