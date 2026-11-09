# 管理后台扩展接口：看板聚合 / 管理员 / 报价 / 活动 / 账单聚合 / AI 记录 / 操作日志。
# 全部走 get_current_admin 服务端鉴权；写操作留痕到 admin_logs。
# 隐私口径：账单只给聚合统计；AI 账单报告不返回私人财务明细；用户以受限标识展示。
import json as _json
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.utils.response import success, error
from app.models.admin import Admin
from app.models.admin_log import AdminLog
from app.models.user import User
from app.models.article import Article
from app.models.post import Post
from app.models.comment import Comment
from app.models.bill import Bill
from app.models.budget_plan import BudgetPlan
from app.models.checkin import Checkin
from app.models.price_history import PriceHistory
from app.models.coupon_activity import CouponActivity
from app.models.ai_assist import AICreation, AIBillReport, AIExecPlan, AIReview
from app.services import admin_log
from app.api.routes.admin import get_current_admin, _hash

router = APIRouter(tags=["管理端扩展"])


def _page(query, skip, limit):
    total = query.count()
    return total, query.offset(skip).limit(limit).all()


def _uref(uid):
    return "U#%s" % (uid or 0)


def _dt(v):
    return v.strftime("%Y-%m-%d %H:%M") if v else ""


# ---------- 数据看板（聚合，全部真实统计） ----------
@router.get("/admin/api/dashboard")
def dashboard(days: int = 7, _=Depends(get_current_admin), db: Session = Depends(get_db)):
    days = max(7, min(30, int(days or 7)))
    counts = {
        "users": db.query(User).filter(User.status != "deleted").count(),
        "articles": db.query(Article).count(),
        "posts": db.query(Post).count(),
        "comments": db.query(Comment).count(),
        "bills": db.query(Bill).count(),
        "pending_articles": db.query(Article).filter(Article.status == "pending").count(),
        "pending_posts": db.query(Post).filter(Post.status == "pending").count(),
        "ai_creations": db.query(AICreation).count(),
        "ai_reports": db.query(AIBillReport).count(),
        "ai_plans": db.query(AIExecPlan).count(),
        "ai_reviews": db.query(AIReview).count(),
        "budgets": db.query(BudgetPlan).filter(
            (BudgetPlan.spend_limit > 0) | (BudgetPlan.target_amount > 0)).count(),
        "checkins": db.query(Checkin).count(),
    }
    # 待审核内容 = 攻略 + 帖子，看板核心区只放一个合计卡，具体条目在「内容审核」里处理
    counts["pending_total"] = counts["pending_articles"] + counts["pending_posts"]

    today = date.today()
    labels, nu, na, np_ = [], [], [], []
    for i in range(days - 1, -1, -1):
        d = today - timedelta(days=i)
        s = datetime.combine(d, datetime.min.time())
        e = datetime.combine(d + timedelta(days=1), datetime.min.time())
        labels.append(d.strftime("%m-%d"))
        nu.append(db.query(User).filter(User.created_at >= s, User.created_at < e).count())
        na.append(db.query(Article).filter(Article.created_at >= s, Article.created_at < e).count())
        np_.append(db.query(Post).filter(Post.created_at >= s, Post.created_at < e).count())

    # 账单分类占比：小额分类（不足 3%）合并成「其他」，只合并展示口径，金额一分不差
    cats = db.query(Bill.category, func.sum(Bill.amount), func.count(Bill.id)).group_by(Bill.category).all()
    bill_total = round(float(sum(float(t or 0) for _, t, _n in cats)), 2)
    main, small_amt, small_cnt = [], 0.0, 0
    for c, t, n in cats:
        amt = round(float(t or 0), 2)
        if bill_total > 0 and amt / bill_total < 0.03:
            small_amt += amt
            small_cnt += int(n or 0)
        else:
            main.append({"name": c or "其他", "value": amt, "count": int(n or 0)})
    main.sort(key=lambda x: -x["value"])
    if round(small_amt, 2) > 0:
        main.append({"name": "其他", "value": round(small_amt, 2), "count": small_cnt})
    bill_pie = [{"name": x["name"], "value": x["value"], "count": x["count"],
                 "pct": round(x["value"] / bill_total * 100, 1) if bill_total else 0} for x in main]

    # 近 6 个月账单「记录数」（不是金额）；当月没过完要说明截至哪天，否则柱形偏矮会被误读成消费少
    months, mcounts = [], []
    for i in range(5, -1, -1):
        total_m = today.year * 12 + today.month - 1 - i
        ym = "%04d-%02d" % (total_m // 12, total_m % 12 + 1)
        months.append(ym)
        mcounts.append(db.query(Bill).filter(func.date_format(Bill.bill_date, "%Y-%m") == ym).count())
    anchor_ym = "%04d-%02d" % (today.year, today.month)
    month_note = ""
    if anchor_ym in months:
        month_note = "%s 为进行中的月份，统计截至 %s" % (anchor_ym[5:] + "月", today.strftime("%m-%d"))

    # 待处理：待审核内容 + 需人工复核的 AI 审核
    pend_a = db.query(Article).filter(Article.status == "pending").order_by(Article.id.desc()).limit(5).all()
    pend_p = db.query(Post).filter(Post.status == "pending").order_by(Post.id.desc()).limit(5).all()
    reviews = db.query(AIReview).order_by(AIReview.id.desc()).limit(30).all()
    need_manual = []
    for r in reviews:
        try:
            res = _json.loads(r.result_json or "{}")
        except _json.JSONDecodeError:
            res = {}
        if res.get("need_manual") or res.get("needs_manual_review"):
            need_manual.append({"id": r.id, "target_type": r.target_type, "target_id": r.target_id})
        if len(need_manual) >= 5:
            break

    latest_users = [{"id": u.id, "nickname": u.nickname, "created_at": _dt(u.created_at)}
                    for u in db.query(User).order_by(User.id.desc()).limit(5).all()]
    latest_articles = [{"id": a.id, "title": a.title, "status": a.status, "created_at": _dt(a.created_at)}
                       for a in db.query(Article).order_by(Article.id.desc()).limit(5).all()]
    latest_posts = [{"id": p.id, "title": p.title, "status": p.status, "created_at": _dt(p.created_at)}
                    for p in db.query(Post).order_by(Post.id.desc()).limit(5).all()]
    ai_runs = []
    for r in db.query(AICreation).order_by(AICreation.id.desc()).limit(3).all():
        ai_runs.append({"kind": "创作", "ref": _uref(r.user_id), "created_at": _dt(r.created_at)})
    for r in db.query(AIBillReport).order_by(AIBillReport.id.desc()).limit(3).all():
        ai_runs.append({"kind": "账单报告", "ref": _uref(r.user_id), "created_at": _dt(r.created_at)})
    for r in db.query(AIExecPlan).order_by(AIExecPlan.id.desc()).limit(3).all():
        ai_runs.append({"kind": "执行计划", "ref": _uref(r.user_id), "created_at": _dt(r.created_at)})
    ai_runs.sort(key=lambda x: x["created_at"], reverse=True)

    return success({
        "counts": counts,
        "trend": {"days": labels, "users": nu, "articles": na, "posts": np_,
                  # 三条线全 0 是真的没有新增，前端据此显示空状态而不是画一张贴着零轴的图
                  "all_zero": not (any(nu) or any(na) or any(np_)),
                  "range": days},
        "bill_pie": bill_pie,
        "bill_total": bill_total,
        "bill_months": {"months": months, "counts": mcounts, "note": month_note},
        "pending": {
            "articles": [{"id": a.id, "title": a.title} for a in pend_a],
            "posts": [{"id": p.id, "title": p.title} for p in pend_p],
            "ai_manual": need_manual,
        },
        "latest": {"users": latest_users, "articles": latest_articles,
                   "posts": latest_posts, "ai": ai_runs[:6]},
    })


# ---------- 管理员管理 ----------
@router.get("/admin/api/admins")
def admin_list(_=Depends(get_current_admin), db: Session = Depends(get_db)):
    rows = db.query(Admin).order_by(Admin.id).all()
    return success({"total": len(rows), "items": [
        {"id": a.id, "username": a.username, "created_at": _dt(a.created_at)} for a in rows]})


class AdminIn(BaseModel):
    username: str
    password: str


@router.post("/admin/api/admins")
def admin_create(body: AdminIn, admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    name = (body.username or "").strip()
    if not name or len(body.password or "") < 6:
        return error("账号不能为空，密码至少 6 位", 400)
    if db.query(Admin).filter(Admin.username == name).first():
        return error("账号已存在", 409)
    a = Admin(username=name[:50], password_hash=_hash(body.password))
    db.add(a)
    db.commit()
    admin_log.record(db, admin, "create", "admin", a.id, "新增管理员：" + name)
    return success({"id": a.id}, "已创建")


class AdminPwd(BaseModel):
    password: str


@router.patch("/admin/api/admins/{aid}/password")
def admin_pwd(aid: int, body: AdminPwd, admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    a = db.query(Admin).filter(Admin.id == aid).first()
    if not a:
        return error("管理员不存在", 404)
    if len(body.password or "") < 6:
        return error("密码至少 6 位", 400)
    a.password_hash = _hash(body.password)
    db.commit()
    admin_log.record(db, admin, "update", "admin", aid, "重置管理员密码：" + a.username)
    return success(True, "已重置密码")


@router.delete("/admin/api/admins/{aid}")
def admin_delete(aid: int, admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    if aid == admin.id:
        return error("不能删除当前登录的管理员", 400)
    if db.query(Admin).count() <= 1:
        return error("至少保留一个管理员", 400)
    a = db.query(Admin).filter(Admin.id == aid).first()
    if not a:
        return error("管理员不存在", 404)
    db.delete(a)
    db.commit()
    admin_log.record(db, admin, "delete", "admin", aid, "删除管理员：" + a.username)
    return success(True, "已删除")


# ---------- 帖子增改（列表/审核/删除在 admin.py） ----------
class PostIn(BaseModel):
    title: str
    content: str = ""
    tags: str = ""
    status: str = ""


@router.post("/admin/api/posts")
def post_create(body: PostIn, admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    if not (body.title or "").strip():
        return error("标题不能为空", 400)
    p = Post(user_id=0, title=body.title.strip()[:200], content=body.content,
             tags=body.tags[:200],
             status=body.status if body.status in ("pending", "approved", "rejected") else "approved")
    db.add(p)
    db.commit()
    admin_log.record(db, admin, "create", "post", p.id, "新增帖子：" + p.title[:40])
    return success({"id": p.id}, "已创建")


@router.put("/admin/api/posts/{pid}")
def post_update(pid: int, body: PostIn, admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    p = db.query(Post).filter(Post.id == pid).first()
    if not p:
        return error("帖子不存在", 404)
    p.title = (body.title or p.title).strip()[:200]
    p.content = body.content
    p.tags = body.tags[:200]
    if body.status in ("pending", "approved", "rejected"):
        p.status = body.status
    db.commit()
    admin_log.record(db, admin, "update", "post", pid, "编辑帖子：" + p.title[:40])
    return success(True, "已更新")


@router.get("/admin/api/posts/{pid}")
def post_detail(pid: int, _=Depends(get_current_admin), db: Session = Depends(get_db)):
    p = db.query(Post).filter(Post.id == pid).first()
    if not p:
        return error("帖子不存在", 404)
    return success({"id": p.id, "title": p.title, "content": p.content, "tags": p.tags,
                    "status": p.status, "user_id": p.user_id, "created_at": _dt(p.created_at)})


# ---------- 评论批量删除 ----------
class IdsIn(BaseModel):
    ids: list


@router.post("/admin/api/comments/batch-delete")
def comments_batch(body: IdsIn, admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    ids = [int(i) for i in (body.ids or [])][:200]
    if not ids:
        return error("没有选中评论", 400)
    n = db.query(Comment).filter(Comment.id.in_(ids)).delete(synchronize_session=False)
    db.commit()
    admin_log.record(db, admin, "delete", "comment", 0, "批量删除评论 %d 条" % n)
    return success({"deleted": n}, "已删除 %d 条" % n)


# ---------- 商品报价（price_histories） ----------
@router.get("/admin/api/prices")
def price_list(q: str = "", platform: str = "", skip: int = 0, limit: int = 20,
               _=Depends(get_current_admin), db: Session = Depends(get_db)):
    query = db.query(PriceHistory)
    if q:
        query = query.filter(PriceHistory.product_name.contains(q))
    if platform:
        query = query.filter(PriceHistory.platform == platform)
    total, rows = _page(query.order_by(PriceHistory.id.desc()), skip, limit)
    return success({"total": total, "items": [
        {"id": r.id, "product_name": r.product_name, "price": r.price,
         "platform": r.platform or "", "url": r.url or "", "recorded_at": _dt(r.recorded_at)}
        for r in rows]})


class PriceIn(BaseModel):
    product_name: str
    price: float
    platform: str = ""
    url: str = ""


@router.post("/admin/api/prices")
def price_create(body: PriceIn, admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    if not (body.product_name or "").strip() or body.price is None or body.price < 0:
        return error("商品名必填，价格不能为负", 400)
    r = PriceHistory(product_name=body.product_name.strip()[:200], price=round(float(body.price), 2),
                     platform=body.platform[:50], url=body.url[:500])
    db.add(r)
    db.commit()
    admin_log.record(db, admin, "create", "price", r.id, "新增报价：" + r.product_name[:40])
    return success({"id": r.id}, "已创建")


@router.put("/admin/api/prices/{rid}")
def price_update(rid: int, body: PriceIn, admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    r = db.query(PriceHistory).filter(PriceHistory.id == rid).first()
    if not r:
        return error("报价不存在", 404)
    if body.price is None or body.price < 0:
        return error("价格不能为负", 400)
    r.product_name = (body.product_name or r.product_name).strip()[:200]
    r.price = round(float(body.price), 2)
    r.platform = body.platform[:50]
    r.url = body.url[:500]
    db.commit()
    admin_log.record(db, admin, "update", "price", rid, "修改报价：" + r.product_name[:40])
    return success(True, "已更新")


@router.delete("/admin/api/prices/{rid}")
def price_delete(rid: int, admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    r = db.query(PriceHistory).filter(PriceHistory.id == rid).first()
    if not r:
        return error("报价不存在", 404)
    db.delete(r)
    db.commit()
    admin_log.record(db, admin, "delete", "price", rid, "删除报价")
    return success(True, "已删除")


# ---------- 优惠活动（coupon_activities） ----------
@router.get("/admin/api/coupons")
def coupon_list(q: str = "", state: str = "", skip: int = 0, limit: int = 20,
                _=Depends(get_current_admin), db: Session = Depends(get_db)):
    query = db.query(CouponActivity)
    if q:
        query = query.filter(CouponActivity.title.contains(q))
    now = datetime.now()
    if state == "active":
        query = query.filter((CouponActivity.deadline == None) | (CouponActivity.deadline >= now))  # noqa: E711
    elif state == "expired":
        query = query.filter(CouponActivity.deadline != None, CouponActivity.deadline < now)  # noqa: E711
    elif state == "verified":
        query = query.filter(CouponActivity.verified == 1)
    total, rows = _page(query.order_by(CouponActivity.id.desc()), skip, limit)
    items = []
    for r in rows:
        expired = bool(r.deadline and r.deadline < now)
        items.append({"id": r.id, "title": r.title, "content": r.content or "",
                      "platform": r.platform or "", "verified": r.verified or 0,
                      "deadline": _dt(r.deadline), "expired": expired,
                      "created_at": _dt(r.created_at)})
    return success({"total": total, "items": items})


class CouponIn(BaseModel):
    title: str
    content: str = ""
    platform: str = ""
    deadline: str = ""
    verified: int = 0


def _parse_deadline(s):
    s = (s or "").strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


@router.post("/admin/api/coupons")
def coupon_create(body: CouponIn, admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    if not (body.title or "").strip():
        return error("活动标题必填", 400)
    dl = _parse_deadline(body.deadline)
    if body.deadline and dl is None:
        return error("截止时间格式应为 YYYY-MM-DD 或 YYYY-MM-DD HH:MM", 400)
    r = CouponActivity(title=body.title.strip()[:200], content=body.content,
                       platform=body.platform[:50], deadline=dl, verified=1 if body.verified else 0)
    db.add(r)
    db.commit()
    admin_log.record(db, admin, "create", "coupon", r.id, "新增活动：" + r.title[:40])
    return success({"id": r.id}, "已创建")


@router.put("/admin/api/coupons/{rid}")
def coupon_update(rid: int, body: CouponIn, admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    r = db.query(CouponActivity).filter(CouponActivity.id == rid).first()
    if not r:
        return error("活动不存在", 404)
    dl = _parse_deadline(body.deadline)
    if body.deadline and dl is None:
        return error("截止时间格式应为 YYYY-MM-DD 或 YYYY-MM-DD HH:MM", 400)
    r.title = (body.title or r.title).strip()[:200]
    r.content = body.content
    r.platform = body.platform[:50]
    r.deadline = dl
    r.verified = 1 if body.verified else 0
    db.commit()
    admin_log.record(db, admin, "update", "coupon", rid, "编辑活动：" + r.title[:40])
    return success(True, "已更新")


@router.delete("/admin/api/coupons/{rid}")
def coupon_delete(rid: int, admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    r = db.query(CouponActivity).filter(CouponActivity.id == rid).first()
    if not r:
        return error("活动不存在", 404)
    db.delete(r)
    db.commit()
    admin_log.record(db, admin, "delete", "coupon", rid, "删除活动")
    return success(True, "已删除")


# ---------- 账单/预算/打卡：只给聚合，不给个人明细 ----------
@router.get("/admin/api/bills/aggregate")
def bills_aggregate(_=Depends(get_current_admin), db: Session = Depends(get_db)):
    cats = db.query(Bill.category, func.sum(Bill.amount), func.count(Bill.id)).group_by(Bill.category).all()
    total = db.query(func.coalesce(func.sum(Bill.amount), 0)).scalar() or 0
    return success({
        "total_amount": round(float(total), 2),
        "total_count": db.query(Bill).count(),
        "categories": [{"name": c or "其他", "amount": round(float(a or 0), 2), "count": n} for c, a, n in cats],
        "budgets_set": db.query(BudgetPlan).filter(BudgetPlan.spend_limit > 0).count(),
        "goals_set": db.query(BudgetPlan).filter(BudgetPlan.target_amount > 0).count(),
        "checkin_records": db.query(Checkin).count(),
        "checkin_saved": round(float(db.query(func.coalesce(func.sum(Checkin.saved_amount), 0)).scalar() or 0), 2),
    })


# ---------- AI 记录（受限标识，不暴露私人财务/对话正文） ----------
@router.get("/admin/api/ai/creations")
def ai_creations(mode: str = "", skip: int = 0, limit: int = 20,
                 _=Depends(get_current_admin), db: Session = Depends(get_db)):
    query = db.query(AICreation)
    if mode:
        query = query.filter(AICreation.mode == mode)
    total, rows = _page(query.order_by(AICreation.id.desc()), skip, limit)
    return success({"total": total, "items": [
        {"id": r.id, "user": _uref(r.user_id), "user_id": r.user_id, "scene": r.scene,
         "mode": r.mode, "article_id": r.article_id or 0, "model": r.model or "",
         "created_at": _dt(r.created_at)} for r in rows]})


@router.get("/admin/api/ai/creations/{rid}")
def ai_creation_detail(rid: int, _=Depends(get_current_admin), db: Session = Depends(get_db)):
    r = db.query(AICreation).filter(AICreation.id == rid).first()
    if not r:
        return error("记录不存在", 404)
    try:
        out = _json.loads(r.output_json or "{}")
    except _json.JSONDecodeError:
        out = {}
    return success({"id": r.id, "user": _uref(r.user_id), "mode": r.mode,
                    "article_id": r.article_id or 0, "output": out, "created_at": _dt(r.created_at)})


@router.get("/admin/api/ai/reports")
def ai_reports(month: str = "", skip: int = 0, limit: int = 20,
               _=Depends(get_current_admin), db: Session = Depends(get_db)):
    query = db.query(AIBillReport)
    if month:
        query = query.filter(AIBillReport.month == month)
    total, rows = _page(query.order_by(AIBillReport.id.desc()), skip, limit)
    # 只给月份/受限用户/时间/模型，不返回 stats_json/report_json 私人财务明细
    return success({"total": total, "items": [
        {"id": r.id, "user": _uref(r.user_id), "user_id": r.user_id, "month": r.month,
         "model": r.model or "", "created_at": _dt(r.created_at)} for r in rows]})


@router.get("/admin/api/ai/plans")
def ai_plans(status: str = "", skip: int = 0, limit: int = 20,
             _=Depends(get_current_admin), db: Session = Depends(get_db)):
    query = db.query(AIExecPlan)
    if status:
        query = query.filter(AIExecPlan.status == status)
    total, rows = _page(query.order_by(AIExecPlan.id.desc()), skip, limit)
    items = []
    for r in rows:
        done = tot = 0
        try:
            plan = _json.loads(r.plan_json or "{}")
            steps = plan.get("steps") or []
            tot = len(steps)
            done = sum(1 for s in steps if s.get("done"))
        except (_json.JSONDecodeError, AttributeError, TypeError):
            pass
        items.append({"id": r.id, "user": _uref(r.user_id), "user_id": r.user_id,
                      "title": r.title or "", "article_id": r.article_id or 0,
                      "status": r.status or "进行中", "progress": (round(done / tot * 100) if tot else 0),
                      "steps_done": done, "steps_total": tot,
                      "actual_saving": r.actual_saving or 0, "created_at": _dt(r.created_at)})
    return success({"total": total, "items": items})


@router.get("/admin/api/ai/reviews")
def ai_reviews(target_type: str = "", skip: int = 0, limit: int = 20,
               _=Depends(get_current_admin), db: Session = Depends(get_db)):
    query = db.query(AIReview)
    if target_type:
        query = query.filter(AIReview.target_type == target_type)
    total, rows = _page(query.order_by(AIReview.id.desc()), skip, limit)
    items = []
    for r in rows:
        try:
            res = _json.loads(r.result_json or "{}")
        except _json.JSONDecodeError:
            res = {}
        # 管理员最终处理结果 = 目标内容当前的审核状态（AI 意见不等于结论）
        if r.target_type == "article":
            final = db.query(Article.status).filter(Article.id == r.target_id).scalar() or "(已删除)"
            title = db.query(Article.title).filter(Article.id == r.target_id).scalar() or ""
        else:
            final = db.query(Post.status).filter(Post.id == r.target_id).scalar() or "(已删除)"
            title = db.query(Post.title).filter(Post.id == r.target_id).scalar() or ""
        items.append({"id": r.id, "target_type": r.target_type, "target_id": r.target_id,
                      "target_title": title, "risk_tags": res.get("risk_tags") or [],
                      "need_manual": bool(res.get("need_manual") or res.get("needs_manual_review")),
                      "spam": bool(res.get("spam")), "final_status": final,
                      "admin_id": r.admin_id or 0, "created_at": _dt(r.created_at)})
    return success({"total": total, "items": items})


# ---------- 操作日志 ----------
@router.get("/admin/api/logs")
def logs(action: str = "", target_type: str = "", skip: int = 0, limit: int = 20,
         _=Depends(get_current_admin), db: Session = Depends(get_db)):
    query = db.query(AdminLog)
    if action:
        query = query.filter(AdminLog.action == action)
    if target_type:
        query = query.filter(AdminLog.target_type == target_type)
    total, rows = _page(query.order_by(AdminLog.id.desc()), skip, limit)
    return success({"total": total, "items": [
        {"id": r.id, "admin": r.admin_name or ("#%s" % r.admin_id), "action": r.action,
         "target_type": r.target_type, "target_id": r.target_id, "detail": r.detail,
         "created_at": _dt(r.created_at)} for r in rows]})
