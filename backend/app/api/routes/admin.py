# 管理端：Web 管理面板 + REST 接口（独立管理员账号）
import os
import hashlib

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db, SessionLocal
from app.core.config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES, ARTICLE_MAX_IMAGES
from app.core.rate_limit import limit_by_ip
from app.utils.response import success, error
from app.utils import images as image_field
from app.models.admin import Admin
from app.models.user import User
from app.models.article import Article
from app.models.post import Post
from app.models.comment import Comment
from app.models.bill import Bill
from app.models.favorite import Favorite
from app.models.chat_record import ChatRecord
from app.models.post_like import PostLike
from app.models.checkin import Checkin
from app.services import admin_log

from jose import jwt, JWTError
from sqlalchemy import func
from datetime import datetime, timedelta, date

router = APIRouter(tags=["管理端"])


# ---------- 密码哈希 & 默认账号 ----------
def _hash(pw: str) -> str:
    return hashlib.sha256((SECRET_KEY + ":" + pw).encode()).hexdigest()


def _seed_admin():
    # 首次启动自动创建默认管理员：admin / admin123
    try:
        db = SessionLocal()
        if db.query(Admin).first() is None:
            db.add(Admin(username="admin", password_hash=_hash("admin123")))
            db.commit()
    except Exception:
        pass
    finally:
        db.close()


def get_current_admin(
    authorization: str = Header(default=""),
    db: Session = Depends(get_db),
):
    # 管理员鉴权依赖：校验 JWT 且 sub 以 admin: 开头
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "未登录")
    token = authorization[len("Bearer "):]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(401, "登录已过期，请重新登录")
    sub = payload.get("sub", "")
    if not sub.startswith("admin:"):
        raise HTTPException(401, "非管理员账号")
    admin = db.query(Admin).filter(Admin.id == int(sub.split(":")[1])).first()
    if not admin:
        raise HTTPException(401, "管理员不存在")
    return admin


class AdminLogin(BaseModel):
    username: str
    password: str


class ArticleIn(BaseModel):
    title: str
    content: str = ""
    category: str = "综合"
    cover: str = ""
    images: list = []
    author: str = "官方"
    # 留空表示「不改状态」。默认给 approved 的话，编辑一篇已驳回的攻略点保存
    # 就会把它悄悄放行了——驳回必须是一个显式动作。
    status: str = ""


# ---------- 页面 ----------
@router.get("/admin", response_class=HTMLResponse)
def admin_page():
    # 返回管理端单页
    html_path = os.path.join(os.path.dirname(__file__), "..", "..", "admin_web", "index.html")
    try:
        with open(html_path, "r", encoding="utf-8") as fp:
            body = fp.read()
    except FileNotFoundError:
        return HTMLResponse("<h2>管理页面缺失：app/admin_web/index.html</h2>")
    # no-store：后台是单文件页面，改完刷新就该看到新版；
    # 否则浏览器拿着缓存旧 HTML，会让人误判「改了没生效」
    return HTMLResponse(body, headers={"Cache-Control": "no-store"})


@router.get("/admin/assets/echarts.min.js")
def admin_echarts():
    # 图表库 vendored 到本地同源提供，不依赖外部 CDN（离线/内网也能出图，也避免 CDN 被投毒）
    p = os.path.join(os.path.dirname(__file__), "..", "..", "admin_web", "echarts.min.js")
    return FileResponse(p, media_type="application/javascript")


# ---------- 登录 ----------
@router.post("/admin/api/login")
def admin_login(payload: AdminLogin, db: Session = Depends(get_db),
                _: None = Depends(limit_by_ip("admin_login", limit=5))):
    admin = db.query(Admin).filter(Admin.username == payload.username).first()
    if not admin or admin.password_hash != _hash(payload.password):
        return error("用户名或密码错误", 401)
    # 带 exp：不加的话管理员 token 一旦泄露就永久有效
    now = datetime.utcnow()
    token = jwt.encode(
        {"sub": f"admin:{admin.id}", "iat": now,
         "exp": now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)},
        SECRET_KEY, algorithm=ALGORITHM,
    )
    return success({"token": token, "username": admin.username})


# ---------- 数据看板 ----------
@router.get("/admin/api/stats")
def admin_stats(_=Depends(get_current_admin), db: Session = Depends(get_db)):
    counts = {
        "users": db.query(User).count(),
        "articles": db.query(Article).count(),
        "posts": db.query(Post).count(),
        "comments": db.query(Comment).count(),
        "bills": db.query(Bill).count(),
        # 待审核投稿：管理端首页要能一眼看到有几条等着放行
        "pending_articles": db.query(Article).filter(Article.status == "pending").count(),
        "pending_posts": db.query(Post).filter(Post.status == "pending").count(),
    }
    # 近 7 天新增用户
    today = date.today()
    days, new_users = [], []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        start = datetime.combine(d, datetime.min.time())
        end = datetime.combine(d + timedelta(days=1), datetime.min.time())
        c = db.query(User).filter(User.created_at >= start, User.created_at < end).count()
        days.append(d.strftime("%m-%d"))
        new_users.append(c)
    # 账单分类占比
    cats = db.query(Bill.category, func.sum(Bill.amount).label("total")).group_by(Bill.category).all()
    bill_pie = [{"name": (c or "其他"), "value": round(float(t or 0), 2)} for c, t in cats]
    return success({
        "counts": counts,
        "new_users": {"days": days, "values": new_users},
        "bill_pie": bill_pie,
    })


# ---------- 用户管理 ----------
@router.get("/admin/api/users")
def admin_users(q: str = "", status: str = "", skip: int = 0, limit: int = 50,
                _=Depends(get_current_admin), db: Session = Depends(get_db)):
    query = db.query(User)
    if q:
        query = query.filter(User.nickname.contains(q))
    if status:
        query = query.filter(User.status == status)
    total = query.count()
    users = query.order_by(User.created_at.desc()).offset(skip).limit(limit).all()
    items = []
    for u in users:
        bill_total = db.query(func.coalesce(func.sum(Bill.amount), 0)).filter(Bill.user_id == u.id).scalar() or 0
        post_count = db.query(func.count(Post.id)).filter(Post.user_id == u.id).scalar() or 0
        items.append({
            "id": u.id, "nickname": u.nickname, "avatar": u.avatar,
            "status": u.status or "active",
            "budget_goal": u.budget_goal, "total_saved": u.total_saved,
            "bill_total": round(float(bill_total), 2), "post_count": post_count,
            "created_at": (u.created_at.strftime("%Y-%m-%d %H:%M") if u.created_at else ""),
        })
    return success({"total": total, "items": items})


@router.get("/admin/api/users/{uid}")
def admin_user_detail(uid: int, _=Depends(get_current_admin), db: Session = Depends(get_db)):
    """用户详情只给聚合数字，不返回私人账单明细/AI 对话正文。"""
    u = db.query(User).filter(User.id == uid).first()
    if not u:
        return error("用户不存在", 404)
    agg = {
        "bills": db.query(func.count(Bill.id)).filter(Bill.user_id == uid).scalar() or 0,
        "bill_total": round(float(db.query(func.coalesce(func.sum(Bill.amount), 0)).filter(Bill.user_id == uid).scalar() or 0), 2),
        "posts": db.query(func.count(Post.id)).filter(Post.user_id == uid).scalar() or 0,
        "comments": db.query(func.count(Comment.id)).filter(Comment.user_id == uid).scalar() or 0,
        "favorites": db.query(func.count(Favorite.id)).filter(Favorite.user_id == uid).scalar() or 0,
        "checkins": db.query(func.count(Checkin.id)).filter(Checkin.user_id == uid).scalar() or 0,
    }
    return success({
        "id": u.id, "nickname": u.nickname, "avatar": u.avatar,
        "status": u.status or "active", "budget_goal": u.budget_goal,
        "total_saved": u.total_saved, "has_password": bool(u.password_hash),
        "created_at": (u.created_at.strftime("%Y-%m-%d %H:%M") if u.created_at else ""),
        "agg": agg,
    })


class UserPatch(BaseModel):
    nickname: str = ""
    avatar: str = ""
    budget_goal: float = -1


@router.patch("/admin/api/users/{uid}")
def admin_user_update(uid: int, body: UserPatch, admin=Depends(get_current_admin),
                      db: Session = Depends(get_db)):
    u = db.query(User).filter(User.id == uid).first()
    if not u:
        return error("用户不存在", 404)
    if body.nickname:
        u.nickname = body.nickname.strip()[:50]
    if body.avatar:
        u.avatar = body.avatar[:500]
    if body.budget_goal >= 0:
        u.budget_goal = round(float(body.budget_goal), 2)
    db.commit()
    admin_log.record(db, admin, "update", "user", uid, "修改用户资料")
    return success(True, "已更新")


@router.patch("/admin/api/users/{uid}/status")
def admin_user_status(uid: int, body: dict, admin=Depends(get_current_admin),
                      db: Session = Depends(get_db)):
    u = db.query(User).filter(User.id == uid).first()
    if not u:
        return error("用户不存在", 404)
    st = (body or {}).get("status", "")
    if st not in ("active", "disabled"):
        return error("状态只能是 active / disabled", 400)
    u.status = st
    db.commit()
    admin_log.record(db, admin, "status", "user", uid, "账号" + ("启用" if st == "active" else "停用"))
    return success({"status": st}, "已更新状态")


@router.delete("/admin/api/users/{uid}")
def admin_user_delete(uid: int, admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    """软删除：只置 status=deleted，保留帖子/账单/评论等业务关联，不做级联物理删除。"""
    u = db.query(User).filter(User.id == uid).first()
    if not u:
        return error("用户不存在", 404)
    u.status = "deleted"
    db.commit()
    admin_log.record(db, admin, "delete", "user", uid, "软删除用户（保留业务数据）")
    return success(True, "用户已停用并标记删除，业务数据保留")


# ---------- 攻略文章管理 ----------
@router.get("/admin/api/articles")
def admin_articles(q: str = "", status: str = "", skip: int = 0, limit: int = 50,
                   _=Depends(get_current_admin), db: Session = Depends(get_db)):
    # status=pending 就是投稿审核队列
    query = db.query(Article)
    if q:
        query = query.filter(Article.title.contains(q))
    if status:
        query = query.filter(Article.status == status)
    total = query.count()
    items = query.order_by(Article.created_at.desc()).offset(skip).limit(limit).all()
    return success({"total": total, "items": [
        {"id": a.id, "title": a.title, "category": a.category, "author": a.author,
         "status": a.status or "approved", "user_id": a.user_id or 0,
         "cover": a.cover or "", "images": image_field.loads(a.images),
         # 编辑表单直接读这一份回填，截断会让保存时把正文尾巴抹掉
         "content": a.content or "",
         "likes": a.likes, "views": a.views,
         "created_at": (a.created_at.strftime("%Y-%m-%d %H:%M") if a.created_at else "")}
        for a in items]})


@router.patch("/admin/api/articles/{aid}/status")
def admin_article_status(aid: int, body: dict, admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    a = db.query(Article).filter(Article.id == aid).first()
    if not a:
        return error("文章不存在", 404)
    st = (body or {}).get("status", "approved")
    if st not in ("pending", "approved", "rejected"):
        return error("状态只能是 pending / approved / rejected", 400)
    a.status = st
    db.commit()
    admin_log.record(db, admin, "status", "article", aid, "攻略审核状态→" + st)
    return success({"status": a.status}, "已更新状态")


def _admin_get_article(aid: int, db: Session):
    a = db.query(Article).filter(Article.id == aid).first()
    if not a:
        return None, error("文章不存在", 404)
    return a, None


@router.post("/admin/api/articles")
def admin_article_create(payload: ArticleIn, admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    try:
        images = image_field.dumps(payload.images, ARTICLE_MAX_IMAGES, "配图")
    except ValueError as e:
        return error(str(e), 400)
    a = Article(title=payload.title, content=payload.content, category=payload.category,
                cover=payload.cover, images=images, author=payload.author,
                status=payload.status if payload.status in ("pending", "approved", "rejected") else "approved")
    db.add(a)
    db.commit()
    admin_log.record(db, admin, "create", "article", a.id, "新增攻略：" + payload.title[:40])
    return success({"id": a.id}, "已创建")


@router.put("/admin/api/articles/{aid}")
def admin_article_update(aid: int, payload: ArticleIn, admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    a, err = _admin_get_article(aid, db)
    if err:
        return err
    try:
        images = image_field.dumps(payload.images, ARTICLE_MAX_IMAGES, "配图")
    except ValueError as e:
        return error(str(e), 400)
    a.title, a.content = payload.title, payload.content
    a.category, a.cover, a.author = payload.category, payload.cover, payload.author
    a.images = images
    if payload.status in ("pending", "approved", "rejected"):
        a.status = payload.status
    db.commit()
    admin_log.record(db, admin, "update", "article", aid, "编辑攻略：" + payload.title[:40])
    return success(True, "已更新")


@router.delete("/admin/api/articles/{aid}")
def admin_article_delete(aid: int, admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    a, err = _admin_get_article(aid, db)
    if err:
        return err
    db.query(Comment).filter(Comment.target_type == "article", Comment.target_id == aid).delete(synchronize_session=False)
    db.delete(a)
    db.commit()
    admin_log.record(db, admin, "delete", "article", aid, "删除攻略：" + a.title[:40])
    return success(True, "已删除")


# ---------- 社区帖子管理 ----------
@router.get("/admin/api/posts")
def admin_posts(q: str = "", status: str = "", skip: int = 0, limit: int = 50,
                _=Depends(get_current_admin), db: Session = Depends(get_db)):
    query = db.query(Post)
    if q:
        query = query.filter(Post.title.contains(q))
    if status:
        query = query.filter(Post.status == status)
    total = query.count()
    posts = query.order_by(Post.created_at.desc()).offset(skip).limit(limit).all()
    items = []
    for p in posts:
        uname = db.query(User.nickname).filter(User.id == p.user_id).scalar() or "未知用户"
        items.append({
            "id": p.id, "title": p.title, "author": uname, "status": p.status,
            "likes": p.likes, "comments_count": p.comments_count,
            "created_at": (p.created_at.strftime("%Y-%m-%d %H:%M") if p.created_at else ""),
        })
    return success({"total": total, "items": items})


@router.patch("/admin/api/posts/{pid}/status")
def admin_post_status(pid: int, body: dict, admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    p = db.query(Post).filter(Post.id == pid).first()
    if not p:
        return error("帖子不存在", 404)
    st = (body or {}).get("status", "approved")
    p.status = st if st in ("pending", "approved", "rejected") else "approved"
    db.commit()
    admin_log.record(db, admin, "status", "post", pid, "帖子审核状态→" + p.status)
    return success({"status": p.status}, "已更新状态")


@router.delete("/admin/api/posts/{pid}")
def admin_post_delete(pid: int, admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    p = db.query(Post).filter(Post.id == pid).first()
    if not p:
        return error("帖子不存在", 404)
    db.query(Comment).filter(Comment.target_type == "post", Comment.target_id == pid).delete(synchronize_session=False)
    db.query(PostLike).filter(PostLike.post_id == pid).delete(synchronize_session=False)
    db.delete(p)
    db.commit()
    admin_log.record(db, admin, "delete", "post", pid, "删除帖子：" + p.title[:40])
    return success(True, "已删除")


# ---------- AI 审核辅助（只给管理员参考，最终决定权在管理员） ----------
import json as _json
from app.models.ai_assist import AIReview
from app.agent.llm import call_llm_simple, LLMError, friendly_error
from app.agent.json_out import extract_json, AIOutputError, _clean_str, _clean_list_str
from app.agent import prompts as ai_prompts


class AIReviewIn(BaseModel):
    target_type: str        # article / post
    target_id: int


def _run_ai_review(target_type: str, target_id: int, admin_id: int, db: Session):
    """对待审核内容跑一次 AI 风险/质量分析并落库。AI 意见仅供参考。"""
    if target_type == "article":
        row = db.query(Article).filter(Article.id == target_id).first()
        title, content = (row.title, row.content) if row else ("", "")
    elif target_type == "post":
        row = db.query(Post).filter(Post.id == target_id).first()
        title, content = (row.title, row.content) if row else ("", "")
    else:
        return error("target_type 只能是 article / post", 400)
    if not row:
        return error("内容不存在", 404)

    filled = ai_prompts.REVIEW_USER.format(
        kind="攻略投稿" if target_type == "article" else "社区帖子",
        title=_clean_str(title, 200), content=(content or "")[:8000])
    try:
        raw = call_llm_simple(filled, ai_prompts.REVIEW_SYSTEM)
        data = extract_json(raw)
    except AIOutputError as e:
        return error(e.brief, 502)
    except LLMError as e:
        return error(e.brief, 502)
    except Exception as e:
        return error(friendly_error(e), 502)

    result = {
        "risk_tags": _clean_list_str(data.get("risk_tags"), 6, 30),
        "spam": bool(data.get("spam")),
        "privacy_risk": bool(data.get("privacy_risk")),
        "quality_advice": _clean_str(data.get("quality_advice"), 500),
        "needs_human": bool(data.get("needs_human")),
        # 模型不给 reason 就如实标「模型未给理由」，不编一个补上
        "reason": _clean_str(data.get("reason"), 500) or "模型未给出理由",
        "title": title,
    }
    rec = AIReview(target_type=target_type, target_id=target_id,
                   result_json=_json.dumps(result, ensure_ascii=False),
                   model="glm-4-flash", admin_id=admin_id)
    db.add(rec)
    db.commit()
    return success({"id": rec.id, "result": result,
                    "created_at": str(rec.created_at)[:19] if rec.created_at else ""})


@router.post("/admin/api/ai-review")
def admin_ai_review(payload: AIReviewIn, admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    return _run_ai_review(payload.target_type, payload.target_id, admin.id, db)


@router.get("/admin/api/ai-review")
def admin_ai_review_get(target_type: str, target_id: int,
                        admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    """查某条内容最近一次的 AI 审核记录（不重新调用模型）。"""
    rec = (db.query(AIReview)
           .filter(AIReview.target_type == target_type, AIReview.target_id == target_id)
           .order_by(AIReview.id.desc()).first())
    if not rec:
        return success(None, "还没有 AI 分析记录")
    try:
        result = _json.loads(rec.result_json or "{}")
    except _json.JSONDecodeError:
        result = {}
    return success({"id": rec.id, "result": result,
                    "created_at": str(rec.created_at)[:19] if rec.created_at else ""})


# ---------- 评论管理 ----------
@router.get("/admin/api/comments")
def admin_comments(q: str = "", skip: int = 0, limit: int = 50,
                   _=Depends(get_current_admin), db: Session = Depends(get_db)):
    query = db.query(Comment)
    if q:
        query = query.filter(Comment.content.contains(q))
    total = query.count()
    rows = query.order_by(Comment.created_at.desc()).offset(skip).limit(limit).all()
    items = []
    for c in rows:
        uname = db.query(User.nickname).filter(User.id == c.user_id).scalar() or "未知用户"
        item = {"id": c.id, "author": uname, "content": c.content,
                "target_type": c.target_type,
                "created_at": (c.created_at.strftime("%Y-%m-%d %H:%M") if c.created_at else "")}
        if c.target_type == "article":
            item["target_title"] = db.query(Article.title).filter(Article.id == c.target_id).scalar() or "(已删除文章)"
        else:
            item["target_title"] = db.query(Post.title).filter(Post.id == c.target_id).scalar() or "(已删除帖子)"
        items.append(item)
    return success({"total": total, "items": items})


@router.delete("/admin/api/comments/{cid}")
def admin_comment_delete(cid: int, admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    c = db.query(Comment).filter(Comment.id == cid).first()
    if not c:
        return error("评论不存在", 404)
    db.delete(c)
    db.commit()
    admin_log.record(db, admin, "delete", "comment", cid, "删除评论")
    return success(True, "已删除")