"""历史预算的离线测试：_fit 只做纯计算，不需要数据库也能验证。

盯的是「一条长消息会不会被反复重发」这个问题——实测一条 5000 字的分享文案
≈ 2500 token，而它会在后面 20 轮里每轮重发一次。
运行：pytest tests/test_memory_budget.py
"""
from types import SimpleNamespace as Row

from app.agent.memory import (
    MAX_HISTORY_CHARS, MAX_RECORD_CHARS, _clip, _fit,
)


def _rows(*contents):
    """按 get_history 给的顺序传：新→旧。"""
    return [Row(role="user" if i % 2 == 0 else "assistant", content=c)
            for i, c in enumerate(contents)]


def test_clips_over_long_record():
    got = _fit(_rows("省" * (MAX_RECORD_CHARS + 500)))
    assert len(got) == 1
    assert len(got[0]["content"]) == MAX_RECORD_CHARS + 1   # 多出来的那 1 个字符是省略号
    assert got[0]["content"].endswith("…")


def test_short_records_pass_through_untouched():
    got = _fit(_rows("你好", "在的"))
    assert [m["content"] for m in got] == ["在的", "你好"]   # 输出要翻回时间正序


def test_total_stays_within_budget():
    # 20 条每条都顶到单条上限，合计远超预算，必须从最旧的开始丢
    got = _fit(_rows(*(["干货" * 400] * 20)))
    assert sum(len(m["content"]) for m in got) <= MAX_HISTORY_CHARS
    assert len(got) < 20


def test_newest_record_survives_even_when_the_rest_is_dropped():
    # 单条上限是 401 字符，所以「超预算」要靠条数堆出来；关键是最新那条一定留着
    got = _fit(_rows(*(["超" * 500] + ["旧" * 500] * 30)))
    assert got[-1]["content"].startswith("超")
    assert len(got) < 31


def test_keeps_recent_and_drops_oldest():
    got = _fit(_rows(*(["新%02d" % i for i in range(30, 0, -1)])))
    assert got[-1]["content"] == "新30"          # 最新的留在末尾（时间正序）
    assert all(m["role"] in ("user", "assistant") for m in got)


def test_empty_and_none_content():
    assert _fit([]) == []
    assert _fit([Row(role="assistant", content=None)]) == [{"role": "assistant", "content": ""}]
