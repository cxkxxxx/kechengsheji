from app.agent.tools.registry import register_tool, make_table, ToolResult


@register_tool(
    name="budget_advice",
    final=True,
    description="查看用户本月省钱目标/预算计划的达成情况，结合支出给出理财与预算控制建议",
    parameters={},
)
def budget_advice(user_id: int = 0, db=None, **kwargs):
    if db is None:
        return "数据库不可用"
    from datetime import datetime
    from sqlalchemy import func
    from app.models.budget_plan import BudgetPlan
    from app.models.bill import Bill
    month = datetime.now().strftime("%Y-%m")
    plan = (db.query(BudgetPlan)
        .filter(BudgetPlan.user_id == user_id, BudgetPlan.month == month)
        .first())
    spend = float(db.query(func.sum(Bill.amount))
        .filter(Bill.user_id == user_id, func.date_format(Bill.bill_date, "%Y-%m") == month)
        .scalar() or 0)

    if not (plan and (float(plan.target_amount or 0) > 0 or float(plan.spend_limit or 0) > 0)):
        return ("本月还没设目标，本月已支出 ¥%.2f。" % spend +
                "可以在「账单」页点「本月目标」设一个，比如「这个月最多花 2000」或「这个月省 500」，"
                "设好后我才能帮你盯进度。")

    saved = float(plan.saved_amount or 0)
    target = float(plan.target_amount or 0)
    limit = float(plan.spend_limit or 0)
    ratio = saved / target * 100 if target > 0 else 0

    rows, head = [], ["项目", "数值"]
    if limit > 0:
        left = limit - spend
        rows += [["支出上限", "¥%.2f" % limit],
                 ["本月已花", "¥%.2f" % spend],
                 ["预算状态", "已超支 ¥%.2f" % -left if left < 0 else "还可花 ¥%.2f" % left]]
    if target > 0:
        rows += [["省钱目标", "¥%.2f" % target],
                 ["已省", "¥%.2f" % saved],
                 ["达成率", "%.0f%%" % ratio]]
    if not rows:
        return ("本月只设了打卡，还没设支出上限或省钱目标，本月已支出 ¥%.2f。" % spend +
                "可以去「账单」页点本月目标设一个。")
    if limit > 0 and spend > limit:
        tip = "已经超预算 ¥%.2f 了，这个月剩下的日子优先砍占比最高的那类。" % (spend - limit)
    elif target > 0 and ratio >= 80:
        tip = "省钱目标快达成了，保持住。"
    elif target > 0 and ratio >= 40:
        tip = "进度过半，把大额支出挪到下个月能快不少。"
    elif target > 0:
        tip = "省钱进度偏慢，先从餐饮/外卖设个每日小目标。"
    else:
        tip = "预算还有余量，继续保持。"

    table = make_table("%s 本月目标" % month, head, rows,
                       "连续打卡 %d 天" % int(plan.checkin_days or 0))
    # final 工具：这段文字就是用户看到的回复，所以只留结论，数字交给表格
    return ToolResult(tip, [], [table])
