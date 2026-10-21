"""best_price 这层自己的挑选逻辑的离线测试。

只替掉上游的两个搜索函数（它们要打第三方共享配额，不能当测试依赖），
相关性打分用包里的纯字符串函数，因为下面几条断言就是靠它的真实行为写的。
运行：pytest tests/test_best_price.py
"""
import best_price_mcp

from app.services import best_price as bp

# 实测抓回来的真实标题：¥16.6 那条是收纳包，包自己曾经把它当最低价推荐
YINGSHI = [
    {"name": "支持消费券&影石AcePro2", "price": 2999, "final_price": 2548.0,
     "shop": "影石Insta360运动相机", "buy_url": "https://s.click.taobao.com/a"},
    {"name": "丽博尔收纳包适用于索尼zve10相机包r50佳能收纳袋富士xs10xt50内胆包",
     "price": 39, "final_price": 16.6, "shop": "天乐美数码专营店", "buy_url": "https://x/2"},
    {"name": "影石Insta360AcePro2配件", "price": 89.1, "final_price": 89.1,
     "shop": "影石Insta360运动", "buy_url": "https://x/3"},
    {"name": "Insta360影石AcePro2AI防抖相机", "price": 2999, "final_price": 2548.0,
     "shop": "天猫超市", "buy_url": "https://x/4"},
]

# 堆了「小米手机」关键词的 Redmi Note 15，光看数字会误判成小米15
XIAOMI = [
    {"name": "【政府补贴15%】REDMI Note 15 5G手机红米note手机小米手机小米官方旗舰店",
     "price": 1599, "final_price": 1299.0, "shop": "信息港数码专营店", "buy_url": "https://x/5"},
    {"name": "小米15手机新品新款上市小米徕卡联合研发小米官方旗舰官网高通骁龙8至尊版手机",
     "price": 3899, "final_price": 2860.0, "shop": "苏宁易购官方旗舰店", "buy_url": "https://x/6"},
]

DAJIANG_ACCESSORIES = [
    {"name": "Action6/5pro/4/3运动相机防水壳", "price": 39.52, "final_price": 39.52,
     "shop": "telesin旗舰店", "buy_url": "https://x/7"},
    {"name": "适用大疆Action5Pro钢化膜Action4运动相机保护膜前后屏", "price": 8.01,
     "final_price": 8.01, "shop": "国货严选旗舰", "buy_url": "https://x/8"},
]


def _stub(monkeypatch, jd=None, taobao=None):
    monkeypatch.setattr(best_price_mcp, "_search_jd", lambda kw: list(jd or []))
    monkeypatch.setattr(best_price_mcp, "_search_taobao", lambda kw: list(taobao or []))


def test_picks_the_real_camera_not_the_pouch(monkeypatch):
    _stub(monkeypatch, taobao=YINGSHI)
    items, warnings = bp.search("影石Ace Pro 2")
    assert items, items
    assert items[0]["final_price"] == 2548.0        # 不能是 ¥16.6 的收纳包
    assert all("收纳包" not in it["title"] for it in items)
    assert all("配件" not in it["title"] for it in items)


def test_relevance_beats_price_for_stuffed_titles(monkeypatch):
    _stub(monkeypatch, taobao=XIAOMI)
    items, _ = bp.search("小米15 手机")
    assert items[0]["title"].startswith("小米15手机")   # 便宜 1500 的 Redmi 不能排前面
    assert items[0]["final_price"] == 2860.0


def test_only_accessories_says_so_honestly(monkeypatch):
    _stub(monkeypatch, taobao=DAJIANG_ACCESSORIES)
    items, warnings = bp.search("大疆Osmo Action 4")
    assert items == []
    assert any("配件" in w for w in warnings)


def test_user_asking_for_a_screen_protector_still_gets_one(monkeypatch):
    _stub(monkeypatch, taobao=DAJIANG_ACCESSORIES)
    items, _ = bp.search("大疆Action4 钢化膜")
    assert items                                     # 他要的就是膜，不能滤掉


def test_jd_and_taobao_both_reported(monkeypatch):
    _stub(monkeypatch, jd=XIAOMI[1:], taobao=XIAOMI[1:])
    items, _ = bp.search("小米15 手机")
    assert {it["platform"] for it in items} == {"京东", "天猫"}


def test_relative_price_gap_is_flagged(monkeypatch):
    rows = [
        {"name": "小米15手机 裸机", "price": 3899, "final_price": 2860.0, "shop": "A店", "buy_url": "https://x/a"},
        {"name": "小米15手机 官方套装", "price": 19999, "final_price": 19999.0, "shop": "B店", "buy_url": "https://x/b"},
        {"name": "小米15手机 尊享套装", "price": 21999, "final_price": 21999.0, "shop": "C店", "buy_url": "https://x/c"},
    ]
    _stub(monkeypatch, taobao=rows)
    items, warnings = bp.search("小米15 手机")
    assert items
    assert any("差得离谱" in w for w in warnings)


def test_clean_keeps_the_title_and_drops_the_noise():
    raw = ("【淘宝】https://e.tb.cn/h.8VrfRTM9?tk=ZYBTT 「DJI/大疆Osmo Action 4运动骑行相机"
           "高清防抖旅游防水vlog摄像机」 点击链接直接打开 或者 淘宝搜索直接打开")
    cleaned = bp._clean(raw)
    assert "http" not in cleaned
    assert "大疆Osmo Action 4" in cleaned            # 书名号里就是标题本身，不能删
    assert "点击链接" not in cleaned and "政府补贴" not in bp._clean("【政府补贴】小米15")


def test_candidates_are_bounded_and_cleaned_first(monkeypatch):
    cands = bp._candidates("小米15 手机")
    assert len(cands) <= 2
    assert cands[0] == "小米15 手机"


def test_upstream_failure_degrades_to_warning(monkeypatch):
    def boom(kw):
        raise RuntimeError("上游炸了")
    monkeypatch.setattr(best_price_mcp, "_search_jd", boom)
    monkeypatch.setattr(best_price_mcp, "_search_taobao", boom)
    items, warnings = bp.search("小米15 手机")
    assert items == [] and warnings


def test_empty_keyword_does_not_call_upstream(monkeypatch):
    called = []
    monkeypatch.setattr(best_price_mcp, "_search_jd", lambda kw: called.append(kw) or [])
    items, warnings = bp.search("   ")
    assert items == [] and warnings and not called


def test_relative_urls_become_clickable(monkeypatch):
    _stub(monkeypatch, taobao=[{"name": "小米15手机", "price": 3899, "final_price": 2860.0,
                                "shop": "店", "buy_url": "s.click.taobao.com/xyz"}])
    items, _ = bp.search("小米15 手机")
    assert items[0]["url"].startswith("https://")


# ---- 双平台并行（借鉴 LangGraph 的 fan-out/fan-in，只在同一关键词内并发）----

def test_two_platforms_are_queried_concurrently(monkeypatch):
    """串行时两个平台的耗时相加；并行后应接近取最大值。

    这条是防回退的：改回 `for platform in (...)` 串行写法就会超时。
    """
    import time
    gap = 0.35

    def slow(_kw):
        time.sleep(gap)
        return [{"name": "小米15手机", "price": 3899, "final_price": 2860.0,
                 "shop": "店", "buy_url": "https://x/1"}]

    monkeypatch.setattr(best_price_mcp, "_search_jd", slow)
    monkeypatch.setattr(best_price_mcp, "_search_taobao", slow)
    t0 = time.time()
    items, _ = bp.search("小米15 手机")
    elapsed = time.time() - t0
    assert items, "并行改造不该把结果弄丢"
    assert elapsed < gap * 2 * 0.8, "耗时 %.2fs 说明两个平台仍在排队串行" % elapsed


def test_slow_jd_does_not_swallow_taobao_results(monkeypatch):
    """一边慢一边快时，快的那边结果必须还在（并发最容易丢的就是这个）。"""
    import time

    def slow_jd(_kw):
        time.sleep(0.2)
        return [{"name": "小米15手机 京东版", "price": 3999, "final_price": 3799.0,
                 "shop": "京东自营", "buy_url": "https://item.jd.com/1.html"}]

    monkeypatch.setattr(best_price_mcp, "_search_jd", slow_jd)
    monkeypatch.setattr(best_price_mcp, "_search_taobao",
                        lambda _kw: [{"name": "小米15手机", "price": 3899, "final_price": 2860.0,
                                      "shop": "天猫店", "buy_url": "https://x/2"}])
    items, _ = bp.search("小米15 手机")
    shops = {i["shop"] for i in items}
    assert "京东自营" in shops and "天猫店" in shops
    assert items[0]["final_price"] <= items[-1]["final_price"]   # 仍然按到手价升序


def test_one_platform_failing_still_returns_the_other(monkeypatch):
    """京东整天被共享配额挡住是常态：它报错不能连累天猫出结果。"""
    def boom(_kw):
        raise RuntimeError("已达接口调用上限")

    monkeypatch.setattr(best_price_mcp, "_search_jd", boom)
    monkeypatch.setattr(best_price_mcp, "_search_taobao",
                        lambda _kw: [{"name": "小米15手机", "price": 3899, "final_price": 2860.0,
                                      "shop": "天猫店", "buy_url": "https://x/3"}])
    items, warnings = bp.search("小米15 手机")
    assert items and items[0]["platform"] == "天猫"
    assert any("京东" in w and "上限" in w for w in warnings)


def test_second_keyword_not_wasted_when_first_hits(monkeypatch):
    """跨关键词仍然要「查到就停」，否则并行会把第三方共享配额按关键词个数翻倍花掉。"""
    calls = []

    def jd(kw):
        calls.append(kw)
        return [{"name": "小米15手机", "price": 3899, "final_price": 2860.0,
                 "shop": "店", "buy_url": "https://x/4"}]

    monkeypatch.setattr(best_price_mcp, "_search_jd", jd)
    monkeypatch.setattr(best_price_mcp, "_search_taobao", lambda kw: calls.append(kw) or [])
    items, _ = bp.search("小米15 手机 官方旗舰店 正品")
    assert items
    assert len(calls) == 2, "第一个候选词就出结果了，不该再打第二个词：%s" % calls
