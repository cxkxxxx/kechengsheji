"""多轮工具循环的离线回归测试。

改这一路的起因：`run_agent_stream` 第二遍传的是 `tools=None`，模型收到
「缺少必填参数：X，请重新调用本工具」后没有任何再调一次的机会，
registry 里承诺的自纠正从来没生效过。现在改成最多 MAX_TOOL_ROUNDS 轮。

全部打桩，不联网、不花额度、不碰数据库。
运行：pytest tests/test_agent_loop.py
"""
from app.agent import engine


def _tool_event(call_id, name, args="{}"):
    return {"delta": {"tool_calls": [{"id": call_id, "index": 0,
                                      "function": {"name": name, "arguments": args}}]},
            "finish_reason": "tool_calls"}


def _text_event(text):
    return {"delta": {"content": text}, "finish_reason": None}


def _stop_event():
    return {"delta": {}, "finish_reason": "stop"}


def _install(monkeypatch, turns, results=None, final_tools=()):
    """把 LLM / 工具执行 / 历史全打桩。turns 是每次模型调用该吐出的事件序列。"""
    calls = {"llm": 0, "tools": [], "with_tools": []}
    scripted = list(turns)

    def fake_stream_llm(messages, tools=None):
        calls["llm"] += 1
        calls["with_tools"].append(bool(tools))
        # 脚本用完后一直吐同一个「还要调工具」的响应，用来验证轮次上限能收住
        evts = scripted.pop(0) if scripted else turns[-1]
        for e in evts:
            yield e

    def fake_execute_tool(name, args_str, user_id, db, context=None):
        calls["tools"].append(name)
        text = (results or {}).get(name, "%s 的结果" % name)
        return (text, name in final_tools, [], [])

    monkeypatch.setattr(engine, "stream_llm", fake_stream_llm)
    monkeypatch.setattr(engine, "execute_tool", fake_execute_tool)
    monkeypatch.setattr(engine, "get_history", lambda uid, db, agent: [])
    return calls


def _dragen(gen):
    return list(gen)


def test_two_tools_in_one_turn(monkeypatch):
    # 「比个价顺便看看我这个月花多少」——过去只能出一个工具，现在两个都要跑到
    calls = _install(monkeypatch, [
        [_tool_event("c1", "price_compare")],
        [_tool_event("c2", "analyze_bills")],
        [_text_event("比价和账单都查好了"), _stop_event()],
    ])
    events = _dragen(engine.run_agent_stream(1, "比价并分析账单", None, agent="coupon"))
    names = [e for e in events if e["type"] == "meta"]

    assert calls["tools"] == ["price_compare", "analyze_bills"]
    # meta 每次发累积列表，前端整体赋值后才看得到「用了两个工具」
    assert names[-1]["tool_used"] == "price_compare、analyze_bills"
    assert any(e["type"] == "chunk" and "比价和账单" in e["text"] for e in events)


def test_second_pass_still_offers_tools(monkeypatch):
    # 这条就是修 bug 的核心：以前第二遍传 tools=None，模型收到「请重新调用本工具」后
    # 根本没有再调一次的能力。现在第二遍必须仍然带着工具定义。
    calls = _install(monkeypatch, [
        [_tool_event("c1", "price_compare")],
        [_text_event("补好了"), _stop_event()],
    ])
    events = _dragen(engine.run_agent_stream(1, "比价", None, agent="coupon"))

    assert calls["llm"] == 2
    assert calls["with_tools"][0] is True      # 第一遍带工具
    assert calls["with_tools"][1] is True      # 第二遍仍然带工具，才谈得上自纠正
    assert any(e["type"] == "chunk" and "补好了" in e["text"] for e in events)


def test_rounds_are_capped_and_still_answer(monkeypatch):
    # 模型犯傻一直要工具：必须在 MAX_TOOL_ROUNDS 处收住，并且最后仍然给出文字
    turns = [[_tool_event("c1", "price_compare")]]
    calls = _install(monkeypatch, turns)
    events = _dragen(engine.run_agent_stream(1, "比价", None, agent="coupon"))

    assert calls["llm"] == engine.MAX_TOOL_ROUNDS + 1   # 2 轮工具 + 1 次强制收尾
    assert len(calls["tools"]) == engine.MAX_TOOL_ROUNDS
    assert events[-1]["type"] == "done"
    # 最后一遍不带工具，保证能收尾
    assert calls["with_tools"][-1] is False


def test_plain_chat_without_tools(monkeypatch):
    calls = _install(monkeypatch, [[_text_event("你好呀"), _stop_event()]])
    events = _dragen(engine.run_agent_stream(1, "在吗", None, agent="coupon"))

    assert calls["tools"] == []
    assert "".join(e["text"] for e in events if e["type"] == "chunk") == "你好呀"
    assert events[-1]["type"] == "done"


def test_final_tool_short_circuits(monkeypatch):
    # 生成型工具（菜谱/购物建议）本身就是完整回复，不该再进一次 LLM
    calls = _install(monkeypatch, [[_tool_event("c1", "generate_recipe")]],
                     final_tools=("generate_recipe",))
    events = _dragen(engine.run_agent_stream(1, "土豆鸡蛋", None, agent="coupon"))

    assert calls["llm"] == 1
    assert any(e["type"] == "chunk" and e["text"] == "generate_recipe 的结果" for e in events)


def test_tables_and_links_emitted_per_round(monkeypatch):
    seen = []

    def fake_execute_tool(name, args_str, user_id, db, context=None):
        seen.append(name)
        if name == "price_compare":
            return ("比价文本", False, [{"url": "https://item.jd.com/1.html"}], [])
        return ("账单文本", False, [], [{"title": "分类", "head": ["a"], "rows": [["1"]]}])

    _install(monkeypatch, [
        [_tool_event("c1", "price_compare")],
        [_tool_event("c2", "analyze_bills")],
        [_text_event("好了"), _stop_event()],
    ])
    monkeypatch.setattr(engine, "execute_tool", fake_execute_tool)
    events = _dragen(engine.run_agent_stream(1, "比价+账单", None, agent="coupon"))

    links = [e for e in events if e["type"] == "links"]
    tables = [e for e in events if e["type"] == "tables"]
    assert len(links) == 1 and len(tables) == 1     # 两轮各出各的，不会被后一轮覆盖


def test_non_stream_run_agent_uses_same_loop(monkeypatch):
    # 非流式那条是给测试/兼容用的，行为必须和流式一致，否则测试通过但线上是旧逻辑
    calls = {"tools": []}

    def fake_call_llm(messages, tools=None):
        n = sum(1 for m in messages if m.get("role") == "tool")
        if n == 0:
            return {"content": "", "tool_calls": [{"id": "c1", "function": {
                "name": "price_compare", "arguments": "{}"}}]}
        if n == 1:
            return {"content": "", "tool_calls": [{"id": "c2", "function": {
                "name": "analyze_bills", "arguments": "{}"}}]}
        return {"content": "两个都查完了", "tool_calls": []}

    def fake_execute_tool(name, args_str, user_id, db, context=None):
        calls["tools"].append(name)
        return ("%s 结果" % name, False, [], [])

    monkeypatch.setattr(engine, "call_llm", fake_call_llm)
    monkeypatch.setattr(engine, "execute_tool", fake_execute_tool)
    monkeypatch.setattr(engine, "get_history", lambda uid, db, agent: [])

    reply, tool_used = engine.run_agent(1, "比价并分析账单", None, agent="coupon")
    assert calls["tools"] == ["price_compare", "analyze_bills"]
    assert reply == "两个都查完了"
    assert tool_used == "price_compare、analyze_bills"
