import json
from app.agent.tools.registry import register_tool
from app.models.bill import Bill


@register_tool(
    name="analyze_bills",
    description="查询并分析用户本月的账单，给出省钱建议",
    parameters={
        "month": {
            "type": "string",
            "description": "要分析的月份，格式 YYYY-MM，留空默认当月",
        },
    },
)
def analyze_bills(month: str = "", user_id: int = 0, db=None, **kwargs) -> str:
    if db is None: return "数据库不可用"
    from datetime import datetime as _dt
    if not month: month = _dt.now().strftime("%Y-%m")
    from sqlalchemy import func
    from app.core.database import SessionLocal
    sess = db or SessionLocal()
    try:
        rows = (sess.query(Bill.category, func.sum(Bill.amount).label("total"), func.count(Bill.id).label("cnt"))
            .filter(Bill.user_id == user_id)
            .filter(func.date_format(Bill.bill_date, "%Y-%m") == month)
            .group_by(Bill.category).all())
    finally:
        if sess is not db: sess.close()
    if not rows: return month + " 还没有账单数据，请先添加账单记录~"
    total = sum(float(r.total or 0) for r in rows)
    L = []
    L.append("[" + month + " 账单分析] 总支出 " + "{:.2f}".format(total) + " 元")
    L.append("")
    for cat, amt, cnt in rows:
        pct = (float(amt or 0) / total * 100) if total > 0 else 0
        L.append("- " + (cat or "其他") + ": " + "{:.2f}".format(float(amt)) + " 元 (" + "{:.0f}".format(pct) + "%, " + str(cnt) + " 笔)")
    L.append("")
    L.append("[省钱建议]")
    found = False
    for cat, amt, cnt in rows:
        a = float(amt or 0)
        if a >= total * 0.35 and total > 0:
            L.append("- " + (cat or "其他") + " 占比过高 (" + "{:.0f}".format(a/total*100) + "%)，建议下月适当控制")
            found = True
    if not found:
        L.append("- 本月消费结构较健康，继续保持!")
    return chr(10).join(L)