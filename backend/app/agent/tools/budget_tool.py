from app.agent.tools.registry import register_tool


@register_tool(
    name="budget_advice",
    final=True,
    description="查看用户本月省钱目标/预算计划的达成情况，结合支出给出理财与预算控制建议",
    parameters={},
)
def budget_advice(user_id: int = 0, db=None, **kwargs) -> str:
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
    spend = (db.query(func.sum(Bill.amount))
        .filter(Bill.user_id == user_id, func.date_format(Bill.bill_date, "%Y-%m") == month)
        .scalar() or 0)
    L = ["[理财管家 · " + month + "]"]
    if plan and plan.target_amount:
        saved = float(plan.saved_amount or 0)
        target = float(plan.target_amount or 0)
        L.append("本月省钱目标：" + ("%.2f" % target) + " 元")
        L.append("已省 " + ("%.2f" % saved) + " 元，连续打卡 " + str(plan.checkin_days or 0) + " 天")
        L.append("本月已支出 " + ("%.2f" % float(spend)) + " 元")
        ratio = saved / target * 100 if target > 0 else 0
        L.append("达成率 " + ("%.0f" % ratio) + "%")
        if ratio >= 80:
            L.append("建议：接近目标，保持得很好！顺利完成可以给自己一个小奖励~")
        elif ratio >= 40:
            L.append("建议：进度过半，减少非必要消费，把大额支出尽量放到下月")
        else:
            L.append("建议：进度偏慢，试试设每日小额省钱小目标，先从餐饮/外卖入手")
    else:
        L.append("本月还没设省钱目标，去「省钱打卡」设一个吧（比如每月存 500 元）")
    L.append("")
    L.append("预算参考：日常支出建议控制在月收入的 50% 内，月底前留出应急金")
    return "\n".join(L)