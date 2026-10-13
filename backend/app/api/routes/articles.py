
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.config import ARTICLE_MAX_IMAGES
from app.models.article import Article
from app.models.user import User
from app.schemas.article import ArticleCreate, ArticleResponse
from app.utils import images as image_field
from app.utils.response import success

router = APIRouter()

# 投稿正文长度上限：一条攻略不该有几十万字，先挡住拿接口灌库的
MAX_CONTENT = 20000


def _safe_cover(url: str) -> str:
    """用户侧封面同样只收本站上传结果，和 images 一个口径。"""
    url = (url or "").strip()
    if not url:
        return ""
    if not url.startswith("/static/") or ".." in url:
        raise HTTPException(400, "封面只能是本站上传后返回的 /static/ 链接")
    return url[:500]


@router.get("")
def get_articles(category: str = "", skip: int = 0, limit: int = 20, db: Session = Depends(get_db)):
    # 只出已过审的：待审核和已驳回的投稿不能出现在公开列表里
    limit = max(1, min(limit, 50))
    query = db.query(Article).filter(Article.status == "approved")
    if category:
        query = query.filter(Article.category == category)
    items = query.order_by(Article.created_at.desc()).offset(skip).limit(limit).all()
    return success([ArticleResponse.model_validate(a) for a in items])


@router.get("/categories")
def get_categories(db: Session = Depends(get_db)):
    # 分类由已有内容决定，前端不再写死一份对不上的清单
    rows = (db.query(Article.category)
            .filter(Article.status == "approved", Article.category.isnot(None))
            .distinct().all())
    return success([r[0] for r in rows if r[0]])


@router.get("/mine")
def my_articles(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # 我的投稿：带 status，用户要看审核结果。形状和 /posts/mine 保持一致，
    # 免得前端一处拿 total、一处拿 length，又算出两个对不上的数
    rows = (db.query(Article).filter(Article.user_id == current_user.id)
            .order_by(Article.created_at.desc()).limit(100).all())
    items = [{
        "id": a.id, "title": a.title, "category": a.category, "status": a.status,
        "cover": a.cover or "", "views": a.views, "likes": a.likes,
        "created_at": str(a.created_at)[:16] if a.created_at else "",
    } for a in rows]
    return success({"total": len(items),
                    "published": sum(1 for a in rows if (a.status or "approved") == "approved"),
                    "items": items})


@router.post("")
def submit_article(payload: ArticleCreate, db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_user)):
    # 用户投稿一律进待审核队列，管理端通过后才出现在攻略列表
    content = (payload.content or "").strip()
    if len(content) < 10:
        raise HTTPException(400, "正文太短了，至少写 10 个字再投")
    try:
        images = image_field.dumps(payload.images, ARTICLE_MAX_IMAGES, "配图")
    except ValueError as e:
        raise HTTPException(400, str(e))
    cover = _safe_cover(payload.cover)
    parsed = image_field.loads(images)
    if not cover and parsed:
        cover = parsed[0]
    a = Article(title=payload.title[:200], content=content[:MAX_CONTENT],
                category=(payload.category or "综合")[:20], cover=cover,
                images=images, author=(current_user.nickname or "用户")[:50],
                user_id=current_user.id, status="pending")
    db.add(a)
    db.commit()
    return success({"id": a.id, "status": a.status},
                   "已提交，管理员审核通过后就会出现在攻略列表")


@router.get("/{article_id}")
def get_article(article_id: int, db: Session = Depends(get_db)):
    article = (db.query(Article)
               .filter(Article.id == article_id, Article.status == "approved").first())
    if not article:
        return success(None, "文章不存在")
    article.views += 1
    db.commit()
    return success(ArticleResponse.model_validate(article))


@router.post("/{article_id}/like")
def like_article(article_id: int, db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)):
    # 点赞攻略文章：要求登录，原来匿名可反复调用把 likes 刷到任意值。
    # 「同一用户只能点一次」还需 ArticleLike 表，暂未做
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        return success(None, "文章不存在")
    article.likes += 1
    db.commit()
    db.refresh(article)
    return success({"likes": article.likes})
