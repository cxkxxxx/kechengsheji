"""补齐历史月份的演示账单：只往「还没有账单的月份」灌数据，已有月份只做检查，绝不删除。

和 /bills/seed-demo 的区别就在这个「不删」上：那个接口是先删目标月再插，
用来在演示前重置当月数据；这个脚本是给已经攒了几个月账单的账户往前补历史，
让 12 个月的趋势图、环比、历史月份目标都有真实数据可看。

用法（在 backend 目录下）：
    python scripts/seed_demo_months.py                 # 所有已有账单的账户，补到近 12 个月
    python scripts/seed_demo_months.py --months 6      # 只补近 6 个月
    python scripts/seed_demo_months.py --users 47,51   # 指定 uid
    python scripts/seed_demo_months.py --anchor 2026-11

生成逻辑复用 app.services.demo_bills.generate_month，和接口是同一套画像/预算规则。
"""
import argparse
import sys
from datetime import date

sys.path.insert(0, ".")

from sqlalchemy import func

from app.core.database import SessionLocal
from app.models.bill import Bill
from app.models.user import User
from app.services import demo_bills


def back_months(anchor: str, count: int) -> list:
    """从锚定月往前数 count 个月，返回 ['2025-12', ..., '2026-11']。"""
    y, m = int(anchor[:4]), int(anchor[5:7])
    out = []
    for i in range(count - 1, -1, -1):
        total = y * 12 + (m - 1) - i
        out.append("%04d-%02d" % (total // 12, total % 12 + 1))
    return out


def month_stats(db, user_id: int, ym: str):
    """某月已有账单的 (条数, 合计, 最早日期, 最晚日期)。

    按 %Y-%m 过滤，和 bills 路由里其它月份查询同一个写法；
    拼日期区间的话「2026-02-31」这种上界 MySQL 会直接报 Incorrect DATE value。
    """
    row = (db.query(func.count(Bill.id), func.coalesce(func.sum(Bill.amount), 0),
                   func.min(Bill.bill_date), func.max(Bill.bill_date))
           .filter(Bill.user_id == user_id,
                   func.date_format(Bill.bill_date, "%Y-%m") == ym)
           .first())
    return row[0] or 0, round(float(row[1] or 0), 2), row[2], row[3]


def resolve_users(db, raw: str) -> list:
    """--users 支持 uid 或昵称，逗号分隔；留空 = 所有已经有账单的账户。"""
    if raw:
        out = []
        for token in [t.strip() for t in raw.split(",") if t.strip()]:
            if token.isdigit():
                u = db.query(User).filter(User.id == int(token)).first()
            else:
                u = db.query(User).filter(User.nickname == token).first()
            if not u:
                raise SystemExit("找不到用户：%s" % token)
            out.append(u)
        return out
    ids = [r[0] for r in db.query(Bill.user_id).distinct().order_by(Bill.user_id).all()]
    return db.query(User).filter(User.id.in_(ids)).order_by(User.id).all()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", type=int, default=12, help="一共覆盖几个月（默认 12）")
    ap.add_argument("--anchor", default=date.today().strftime("%Y-%m"), help="锚定月 YYYY-MM，默认本月")
    ap.add_argument("--users", default="", help="uid 或昵称，逗号分隔；默认所有有账单的账户")
    ap.add_argument("--rebuild", default="",
                    help="这些月份先清空再重造（逗号分隔 YYYY-MM）。只动列出来的月份，其它一律不删")
    ap.add_argument("--dry-run", action="store_true", help="只报告将要补哪些月，不写库")
    args = ap.parse_args()

    targets = back_months(args.anchor, args.months)
    rebuild = [x.strip() for x in args.rebuild.split(",") if x.strip()]
    bad = [x for x in rebuild if x not in targets]
    if bad:
        raise SystemExit("--rebuild 里的月份不在覆盖范围内：%s" % ", ".join(bad))

    today = date.today()
    db = SessionLocal()
    try:
        users = resolve_users(db, args.users)
        print("锚定 %s，覆盖 %d 个月：%s ～ %s" % (args.anchor, len(targets), targets[0], targets[-1]))
        print("目标账户 %d 个：%s" % (len(users), ", ".join("uid%s" % u.id for u in users)))
        print("-" * 72)

        inserted_total = 0
        for u in users:
            # 指定要重造的月份先清掉（只清这些月、只清这个账户），清完它就按空月被补上
            cleared = []
            for ym in rebuild:
                n = (db.query(Bill).filter(Bill.user_id == u.id,
                                           func.date_format(Bill.bill_date, "%Y-%m") == ym)
                     .delete(synchronize_session=False))
                db.commit()
                if n:
                    cleared.append((ym, n))

            plan, skipped = [], []
            for ym in targets:
                cnt, total, _, _ = month_stats(db, u.id, ym)
                if cnt:
                    skipped.append((ym, cnt, total))
                else:
                    plan.append(ym)

            print("uid=%s %s" % (u.id, u.nickname or "(无昵称)"))
            for ym, n in cleared:
                print("   重造 %s：先清掉 %d 条" % (ym, n))
            for ym, cnt, total in skipped:
                print("   已有 %s：%d 条 / %.2f 元 —— 跳过" % (ym, cnt, total))

            if args.dry_run:
                print("   待补：%s" % (", ".join(plan) or "无"))
                continue

            made = 0
            for ym in plan:
                spec = demo_bills.generate_month(db, u.id, ym, today=today)
                for r in spec["rows"]:
                    db.add(Bill(user_id=u.id, amount=r["amount"], category=r["category"],
                                source=r["source"], pay_channel=r["pay_channel"],
                                order_no=r["order_no"], bill_date=r["bill_date"]))
                    made += 1
                db.commit()
                cnt, total, first, last = month_stats(db, u.id, ym)
                print("   补 %s：%d 条 / %.2f 元（%s ～ %s）" % (ym, cnt, total, first, last))
            print("   本次新增 %d 条" % made)
            inserted_total += made

        print("-" * 72)
        print("合计新增 %d 条演示账单" % inserted_total)

        # 收尾体检：有没有日期跑进未来、有没有月份仍然空着
        bad = db.query(func.count(Bill.id)).filter(Bill.bill_date > today).scalar()
        print("未来日期账单：%d 条%s" % (bad, "（异常，请检查）" if bad else ""))
        for u in users:
            have = [ym for ym in targets if month_stats(db, u.id, ym)[0]]
            if len(have) < len(targets):
                miss = sorted(set(targets) - set(have))
                print("uid=%s 仍缺月份：%s" % (u.id, ", ".join(miss)))
    finally:
        db.close()


if __name__ == "__main__":
    main()
