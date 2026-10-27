

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime
from pydantic import BaseModel

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.budget_plan import BudgetPlan
from app.models.bill import Bill
from app.utils.response import success

router = APIRouter()

MAX_LIMIT = 10 ** 8


class PlanCreate(BaseModel):
    # 设置月度目标请求：两种目标都可以设，至少给一个
    target_amount: float = 0    # 月度省钱目标（元）
    spend_limit: float = 0      # 月度支出上限（元）


def _month_spend(db: Session, user_id: int, month: str) -> float:
    return float(db.query(func.sum(Bill.amount)).filter(
        Bill.user_id == user_id,
        func.date_format(Bill.bill_date, "%Y-%m") == month,
    ).scalar() or 0)


def _plan_payload(plan, month: str, spend: float) -> dict:
    target = float(plan.target_amount or 0) if plan else 0
    limit = float(plan.spend_limit or 0) if plan else 0
    saved = float(plan.saved_amount or 0) if plan else 0
    return {
        "month": month,
        "target_amount": target,
        "spend_limit": limit,
        "saved_amount": saved,
        "spend": round(spend, 2),
        "checkin_days": int(plan.checkin_days or 0) if plan else 0,
        "last_checkin_date": plan.last_checkin_date if plan else None,
        # 省钱进度：已省 / 目标
        "save_progress": round(saved / target * 100, 1) if target > 0 else 0,
        # 预算使用率：已花 / 上限，超 100% 表示已爆预算
        "budget_used": round(spend / limit * 100, 1) if limit > 0 else 0,
        "budget_left": round(limit - spend, 2) if limit > 0 else 0,
    }

@router.get("/plan")
def get_plan(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
        # 获取当前月的省钱计划

    month = datetime.now().strftime("%Y-%m")
    plan = db.query(BudgetPlan).filter(
        BudgetPlan.user_id == current_user.id,
        BudgetPlan.month == month,
    ).first()
    # 没有计划也回一份全 0 的结构，前端不用到处判空
    return success(_plan_payload(plan, month, _month_spend(db, current_user.id, month)))

@router.post("/plan")
def set_plan(
    req: PlanCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
        # 设置月度目标：省钱目标 / 支出上限，可以同时设

    for label, v in (("省钱目标", req.target_amount), ("支出上限", req.spend_limit)):
        if v < 0:
            raise HTTPException(400, "%s不能是负数" % label)
        if v > MAX_LIMIT:
            raise HTTPException(400, "%s数值太大" % label)
    target = round(float(req.target_amount or 0), 2)
    limit = round(float(req.spend_limit or 0), 2)
    if target <= 0 and limit <= 0:
        raise HTTPException(400, "至少设一个目标：本月省多少，或本月最多花多少")

    month = datetime.now().strftime("%Y-%m")
    plan = db.query(BudgetPlan).filter(
        BudgetPlan.user_id == current_user.id,
        BudgetPlan.month == month,
    ).first()
    if not plan:
        plan = BudgetPlan(user_id=current_user.id, month=month)
        db.add(plan)
    plan.target_amount = target
    plan.spend_limit = limit
    db.commit()
    return success(_plan_payload(plan, month, _month_spend(db, current_user.id, month)), "目标已保存")

class CheckinRequest(BaseModel):
        # 省钱记录请求：每日打卡是默认来源，攻略/帖子/AI 方案走 source+ref 关联

    saved_amount: float       # 这笔实际省了多少元
    note: str = ""            # 备注
    day: str = ""             # YYYY-MM-DD，留空=今天；允许补记过去的日子
    source: str = "打卡"      # 打卡/攻略/社区经验/AI方案
    ref_type: str = ""        # 关联内容类型：article/post
    ref_id: int = 0           # 关联内容 id


def _recompute_month(db: Session, user, plan, month: str, before_total: float) -> None:
    """plan 累计值与用户总节省一律由明细重算，绝不用 +=（历史上翻过倍）。"""
    from app.models.checkin import Checkin
    # date_format 是 MySQL 方言；sqlite（单测内存库）用 strftime 等价表达
    if db.bind is not None and db.bind.dialect.name == "sqlite":
        month_expr = func.strftime("%Y-%m", Checkin.day)
    else:
        month_expr = func.date_format(Checkin.day, "%Y-%m")
    total, days = db.query(func.coalesce(func.sum(Checkin.saved_amount), 0), func.count(func.distinct(Checkin.day))) \
        .filter(Checkin.user_id == user.id,
                month_expr == month).first()
    plan.saved_amount = round(float(total or 0), 2)
    plan.checkin_days = int(days or 0)
    plan.last_checkin_date = datetime.now()
    user.total_saved = max(0.0, round(float(user.total_saved or 0) + (plan.saved_amount - before_total), 2))


def _parse_day(raw: str):
    from datetime import date as _date, datetime as _dt, timedelta
    raw = (raw or "").strip()
    if not raw:
        return _date.today()
    try:
        d = _dt.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(400, "日期格式应为 YYYY-MM-DD")
    if d > _date.today() + timedelta(days=1):
        raise HTTPException(400, "不能记未来的账")
    return d


_SOURCE_WHITELIST = {"打卡", "攻略", "社区经验", "AI方案"}


@router.post("/do")
def do_checkin(
    req: CheckinRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """记一笔实际省钱。

    - source=「打卡」：保持老语义，同一天的打卡只算一条，再提交是改金额；
    - 其它来源（攻略/社区经验/AI方案）：每次都新增一条，和打卡互不覆盖。
    一天多笔现在合法（迁移已去掉一天一条的约束），plan.saved_amount 由明细重算。
    """
    from datetime import date as _date
    from app.models.checkin import Checkin

    if req.saved_amount < 0:
        raise HTTPException(400, "省钱金额不能是负数")
    if req.saved_amount > MAX_LIMIT:
        raise HTTPException(400, "省钱金额数值太大")
    source = req.source if req.source in _SOURCE_WHITELIST else "打卡"
    day = _parse_day(req.day)
    month = day.strftime("%Y-%m")

    plan = db.query(BudgetPlan).filter(
        BudgetPlan.user_id == current_user.id,
        BudgetPlan.month == month,
    ).first()
    if not plan:
        plan = BudgetPlan(user_id=current_user.id, month=month, target_amount=500)
        db.add(plan)
        db.commit()
        db.refresh(plan)

    before_total = float(plan.saved_amount or 0)
    repeated = False
    if source == "打卡" and day == _date.today():
        # 每日打卡保持幂等：改当天那条打卡记录，不新增
        row = db.query(Checkin).filter(
            Checkin.user_id == current_user.id, Checkin.day == day,
            Checkin.source == "打卡").first()
        if row:
            row.saved_amount = round(float(req.saved_amount), 2)
            row.note = (req.note or "")[:120]
            repeated = True
        else:
            db.add(Checkin(user_id=current_user.id, day=day,
                           saved_amount=round(float(req.saved_amount), 2),
                           note=(req.note or "")[:120], source="打卡"))
    else:
        db.add(Checkin(user_id=current_user.id, day=day,
                       saved_amount=round(float(req.saved_amount), 2),
                       note=(req.note or "")[:120],
                       source=source, ref_type=(req.ref_type or "")[:20],
                       ref_id=int(req.ref_id) if req.ref_id else None))
    db.commit()

    _recompute_month(db, current_user, plan, month, before_total)
    db.commit()

    return success({
        "saved_amount": plan.saved_amount,
        "target_amount": plan.target_amount,
        "checkin_days": plan.checkin_days,
        "progress": round(plan.saved_amount / plan.target_amount * 100, 1) if plan.target_amount > 0 else 0,
        "repeated": repeated,
        "today_saved": round(float(req.saved_amount), 2),
    }, "今天已经打过卡了，已按你新填的金额更新" if repeated else "已记入省钱记录")


def _ref_titles(db: Session, rows: list) -> dict:
    """把关联的攻略/帖子标题批量查出来，列表里能看出这笔钱省在哪条经验上。"""
    art_ids = {r.ref_id for r in rows if r.ref_type == "article" and r.ref_id}
    post_ids = {r.ref_id for r in rows if r.ref_type == "post" and r.ref_id}
    titles = {}
    if art_ids:
        from app.models.article import Article
        for i, t in db.query(Article.id, Article.title).filter(Article.id.in_(art_ids)):
            titles["article-%s" % i] = t
    if post_ids:
        from app.models.post import Post
        for i, t in db.query(Post.id, Post.title).filter(Post.id.in_(post_ids)):
            titles["post-%s" % i] = t
    return titles


@router.get("/records")
def month_records(
    month: str = "",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """某月的省钱记录明细（含来源与关联内容），给账单页的「省钱记录」列表用。"""
    from datetime import date as _date
    from app.models.checkin import Checkin
    month = (month or "").strip() or _date.today().strftime("%Y-%m")
    rows = (db.query(Checkin).filter(
            Checkin.user_id == current_user.id,
            func.date_format(Checkin.day, "%Y-%m") == month)
            .order_by(Checkin.day.desc(), Checkin.id.desc()).all())
    titles = _ref_titles(db, rows)
    records = [{
        "id": r.id,
        "day": r.day.strftime("%Y-%m-%d"),
        "saved_amount": round(float(r.saved_amount or 0), 2),
        "note": r.note or "",
        "source": r.source or "打卡",
        "ref_type": r.ref_type or "",
        "ref_id": r.ref_id or 0,
        "ref_title": titles.get("%s-%s" % (r.ref_type, r.ref_id), ""),
    } for r in rows]
    return success({
        "month": month,
        "records": records,
        "count": len(records),
        "total": round(sum(r["saved_amount"] for r in records), 2),
    })


@router.put("/records/{record_id}")
def update_record(
    record_id: int,
    req: CheckinRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """改一笔省钱记录（金额/备注）。只能改自己的；改完重算当月累计与用户总节省。

    来源和关联内容不允许在这里改——要改来源就删掉重记，避免关联被悄悄换掉。
    """
    from app.models.checkin import Checkin
    row = db.query(Checkin).filter(
        Checkin.id == record_id, Checkin.user_id == current_user.id).first()
    if not row:
        raise HTTPException(404, "记录不存在")
    if req.saved_amount < 0:
        raise HTTPException(400, "省钱金额不能是负数")
    if req.saved_amount > MAX_LIMIT:
        raise HTTPException(400, "省钱金额数值太大")
    month = row.day.strftime("%Y-%m")
    plan = db.query(BudgetPlan).filter(
        BudgetPlan.user_id == current_user.id, BudgetPlan.month == month).first()
    before_total = float(plan.saved_amount or 0) if plan else 0.0
    row.saved_amount = round(float(req.saved_amount), 2)
    row.note = (req.note or "")[:120]
    db.commit()
    if plan:
        _recompute_month(db, current_user, plan, month, before_total)
        db.commit()
    return success({
        "id": row.id, "saved_amount": row.saved_amount, "note": row.note,
    }, "已更新")


@router.delete("/records/{record_id}")
def delete_record(
    record_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删一笔省钱记录。只能删自己的；删完重算当月累计与用户总节省。"""
    from app.models.checkin import Checkin
    row = db.query(Checkin).filter(
        Checkin.id == record_id, Checkin.user_id == current_user.id).first()
    if not row:
        raise HTTPException(404, "记录不存在")
    month = row.day.strftime("%Y-%m")
    plan = db.query(BudgetPlan).filter(
        BudgetPlan.user_id == current_user.id, BudgetPlan.month == month).first()
    before_total = float(plan.saved_amount or 0) if plan else 0.0
    db.delete(row)
    db.commit()
    if plan:
        _recompute_month(db, current_user, plan, month, before_total)
        db.commit()
    return success({"deleted": record_id}, "已删除")


@router.get("/month")
def month_checkins(
    month: str = "",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """某月的省钱记录按天汇总，给账单页的「打卡日历」用。

    一天可能多笔（打卡 + 按攻略/AI 方案记的），这里聚合成当天合计。
    """
    from datetime import date as _date
    from app.models.checkin import Checkin
    month = (month or "").strip() or _date.today().strftime("%Y-%m")
    rows = (db.query(Checkin.day, func.coalesce(func.sum(Checkin.saved_amount), 0))
            .filter(Checkin.user_id == current_user.id,
                    func.date_format(Checkin.day, "%Y-%m") == month)
            .group_by(Checkin.day).order_by(Checkin.day).all())
    days = [{"day": d.day, "saved_amount": round(float(v or 0), 2)} for d, v in rows]
    return success({
        "month": month,
        "days": days,
        "count": len(days),
        "total": round(sum(d["saved_amount"] for d in days), 2),
        "today": _date.today().day if _date.today().strftime("%Y-%m") == month else None,
        "checked_today": any(d["day"] == _date.today().day
                             for d in days) if _date.today().strftime("%Y-%m") == month else False,
    })