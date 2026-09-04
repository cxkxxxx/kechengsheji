

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.article import Article
from app.schemas.article import ArticleResponse
from app.utils.response import success

router = APIRouter()

@router.get("")
def get_articles(category: str = "", skip: int = 0, limit: int = 20, db: Session = Depends(get_db)):
    # # 获取攻略文章列表（支持按分类筛选）
    query = db.query(Article)
    if category:
        query = query.filter(Article.category == category)
    items = query.order_by(Article.created_at.desc()).offset(skip).limit(limit).all()
    return success([ArticleResponse.model_validate(a) for a in items])

@router.get("/{article_id}")
def get_article(article_id: int, db: Session = Depends(get_db)):
        # 获取文章详情

    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        return success(None, "文章不存在")
    # 浏览量 +1
    article.views += 1
    db.commit()
    return success(ArticleResponse.model_validate(article))

@router.post("/{article_id}/like")
def like_article(article_id: int, db: Session = Depends(get_db)):
        # 点赞攻略文章

    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        return success(None, "文章不存在")
    article.likes += 1
    db.commit()
    db.refresh(article)
    return success({"likes": article.likes})